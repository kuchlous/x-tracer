"""VCD loading backend using pyvcd (pure Python fallback)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from .database import VCDDatabase


def _import_pyvcd_reader():
    """Import the external pyvcd 'vcd.reader' module, avoiding collision with our package."""
    # Our src/vcd shadows the installed pyvcd 'vcd' package.
    # Temporarily remove src paths so importlib finds the real pyvcd.
    saved = sys.modules.pop("vcd", None)
    saved_reader = sys.modules.pop("vcd.reader", None)
    try:
        # Find the external vcd package by removing local src entries temporarily
        orig_path = list(sys.path)
        src_dir = str(Path(__file__).parent.parent)
        sys.path = [p for p in sys.path if p != src_dir]
        try:
            reader = importlib.import_module("vcd.reader")
        finally:
            sys.path = orig_path
        return reader
    finally:
        # Restore original module state
        if saved is not None:
            sys.modules["vcd"] = saved
        if saved_reader is not None:
            sys.modules["vcd.reader"] = saved_reader


_reader = _import_pyvcd_reader()
TokenKind = _reader.TokenKind
tokenize = _reader.tokenize


def load(vcd_path: Path, signals: set[str] | None = None) -> VCDDatabase:
    """Load VCD using pyvcd tokenizer and return a VCDDatabase.

    Falls back to manual line-by-line parsing if pyvcd fails (e.g., due to
    non-standard signal names like Cadence's ``signal[field_name]``).
    """
    try:
        return _load_pyvcd_tokenizer(vcd_path, signals)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "pyvcd tokenizer failed (%s), falling back to line parser", e
        )
        return _load_line_parser(vcd_path, signals)


def _load_pyvcd_tokenizer(vcd_path: Path, signals: set[str] | None = None) -> VCDDatabase:
    """Load VCD using pyvcd tokenizer."""
    scope_stack: list[str] = []
    id_to_tracked: dict[str, list[str]] = {}
    all_signal_names: set[str] = set()
    transitions: dict[str, list[tuple[int, str]]] = {}
    current_time = 0

    with open(vcd_path, 'rb') as f:
        for token in tokenize(f):
            kind = token.kind

            if kind == TokenKind.SCOPE:
                scope_stack.append(token.data.ident)

            elif kind == TokenKind.UPSCOPE:
                if scope_stack:
                    scope_stack.pop()

            elif kind == TokenKind.VAR:
                var = token.data
                hier_name = '.'.join(scope_stack + [var.reference])
                all_signal_names.add(hier_name)

                # Track this signal?
                if signals is None or hier_name in signals:
                    if var.id_code not in id_to_tracked:
                        id_to_tracked[var.id_code] = []
                    id_to_tracked[var.id_code].append(hier_name)
                    transitions[hier_name] = []

            elif kind == TokenKind.CHANGE_TIME:
                current_time = token.data

            elif kind == TokenKind.CHANGE_SCALAR:
                sc = token.data
                names = id_to_tracked.get(sc.id_code)
                if names:
                    val = sc.value.lower()
                    for name in names:
                        transitions[name].append((current_time, val))

            elif kind == TokenKind.CHANGE_VECTOR:
                vc = token.data
                names = id_to_tracked.get(vc.id_code)
                if names:
                    val = _normalize_vector_value(vc.value)
                    for name in names:
                        transitions[name].append((current_time, val))

    return VCDDatabase(transitions, all_signal_names)


def _load_line_parser(vcd_path: Path, signals: set[str] | None = None) -> VCDDatabase:
    """Fallback line-by-line VCD parser that handles non-standard signal names.

    Tolerates Cadence-style names with non-numeric brackets like
    ``app_gpio0_ctrl[ds0_topad]``.

    Optimized for multi-GB VCD files:
    - Signal filtering: only stores transitions for requested signals
    - Binary I/O with large buffer for the value-change section
    - Progress logging every 10M lines for long-running parses
    """
    import logging
    import re
    from .database import _TS_UNITS

    logger = logging.getLogger(__name__)

    scope_stack: list[str] = []
    id_to_tracked: dict[str, list[str]] = {}
    all_signal_names: set[str] = set()
    transitions: dict[str, list[tuple[int, str]]] = {}
    current_time = 0
    timescale_fs = 1000  # default: 1 ps

    _var_re = re.compile(
        r'^\$var\s+\w+\s+\d+\s+(\S+)\s+(.*?)\s+\$end'
    )
    _scope_re = re.compile(r'^\$scope\s+\w+\s+(\S+)\s+\$end')
    _upscope_re = re.compile(r'^\$upscope\s+\$end')
    _enddefs_re = re.compile(r'^\$enddefinitions\s+\$end')
    _timescale_re = re.compile(r'(\d+)\s*(s|ms|us|ns|ps|fs)', re.IGNORECASE)
    _bitrange_re = re.compile(r'\s*\[\d+(?::\d+)?\]\s*$')

    # --- Phase 1: Parse header in text mode (handles encoding issues) ---
    # Use readline() instead of iterator to allow tell() for body offset
    in_timescale = False
    body_offset = 0
    with open(vcd_path, 'r', errors='replace') as f:
        while True:
            line = f.readline()
            if not line:
                break
            stripped = line.strip()
            if not stripped:
                continue

            # Parse timescale (may span multiple lines)
            if stripped.startswith('$timescale'):
                in_timescale = True
                m = _timescale_re.search(stripped)
                if m:
                    timescale_fs = int(m.group(1)) * _TS_UNITS[m.group(2).lower()]
                    in_timescale = False
                continue
            if in_timescale:
                m = _timescale_re.search(stripped)
                if m:
                    timescale_fs = int(m.group(1)) * _TS_UNITS[m.group(2).lower()]
                if '$end' in stripped:
                    in_timescale = False
                continue

            m = _scope_re.match(stripped)
            if m:
                scope_stack.append(m.group(1))
                continue

            m = _upscope_re.match(stripped)
            if m:
                if scope_stack:
                    scope_stack.pop()
                continue

            m = _var_re.match(stripped)
            if m:
                id_code = m.group(1)
                reference = m.group(2)
                # Strip bit range from reference if present: "name [7:0]" -> "name"
                # But keep non-numeric brackets as part of the name
                ref_clean = _bitrange_re.sub('', reference)
                hier_name = '.'.join(scope_stack + [ref_clean])
                all_signal_names.add(hier_name)

                if signals is None or hier_name in signals:
                    if id_code not in id_to_tracked:
                        id_to_tracked[id_code] = []
                    id_to_tracked[id_code].append(hier_name)
                    transitions[hier_name] = []
                continue

            if _enddefs_re.match(stripped):
                body_offset = f.tell()
                break

    # If no signals are being tracked, we can skip the value-change section
    if not id_to_tracked:
        return VCDDatabase(transitions, all_signal_names, timescale_fs=timescale_fs)

    # Build a set of tracked id_code bytes for fast membership testing
    _id_to_tracked_get = id_to_tracked.get

    # --- Phase 2: Parse value changes using buffered binary I/O ---
    # Binary mode with a large buffer avoids per-line encoding overhead
    # and is significantly faster for multi-GB files.
    line_count = 0
    _PROGRESS_INTERVAL = 10_000_000

    file_size = vcd_path.stat().st_size
    if file_size > 50_000_000:  # 50 MB
        logger.info("Parsing VCD value changes (%d MB) ...",
                     file_size // (1024 * 1024))

    with open(vcd_path, 'rb', buffering=8 * 1024 * 1024) as fb:
        # Seek past the header we already parsed
        if body_offset:
            fb.seek(body_offset)

        for raw_line in fb:
            line_count += 1

            # Progress reporting for large files
            if line_count % _PROGRESS_INTERVAL == 0:
                logger.info("  ... processed %dM lines", line_count // 1_000_000)

            # Strip whitespace (binary): strip() handles \r\n, \n, spaces
            line = raw_line.strip()
            if not line:
                continue

            first_byte = line[0]

            # Timestamp line: #<digits>
            if first_byte == 35:  # ord('#')
                try:
                    current_time = int(line[1:])
                except ValueError:
                    pass
                continue

            # Skip $dumpvars / $end / other $ directives
            if first_byte == 36:  # ord('$')
                continue

            # Scalar value change: <value><id_code>
            # first_byte in {0, 1, x, X, z, Z}
            if first_byte in (48, 49, 120, 88, 122, 90):
                # 48='0', 49='1', 120='x', 88='X', 122='z', 90='Z'
                id_code = line[1:].decode('ascii', errors='replace')
                names = _id_to_tracked_get(id_code)
                if names:
                    val = chr(first_byte).lower()
                    for name in names:
                        transitions[name].append((current_time, val))
                continue

            # Vector value change: b<value> <id_code> or B/r/R
            if first_byte in (98, 66, 114, 82):  # b, B, r, R
                space_idx = line.find(b' ')
                if space_idx == -1:
                    space_idx = line.find(b'\t')
                if space_idx > 0:
                    id_code = line[space_idx + 1:].decode('ascii', errors='replace')
                    names = _id_to_tracked_get(id_code)
                    if names:
                        val = line[1:space_idx].decode('ascii', errors='replace').lower()
                        for name in names:
                            transitions[name].append((current_time, val))
                continue

    if file_size > 50_000_000:
        logger.info("VCD parsing complete: %d lines processed", line_count)

    return VCDDatabase(transitions, all_signal_names, timescale_fs=timescale_fs)


def parse_vcd_header(vcd_path: Path) -> tuple[set[str], int]:
    """Parse only the VCD header (up to $enddefinitions $end).

    Returns (signal_names, timescale_fs) for fast signal existence checking
    without loading the full file.

    Handles Cadence non-standard names with non-numeric brackets.
    """
    import re
    from .database import _TS_UNITS

    scope_stack: list[str] = []
    signal_names: set[str] = set()
    timescale_fs = 1000  # default 1ps

    _var_re = re.compile(r'^\$var\s+\w+\s+\d+\s+(\S+)\s+(.*?)\s+\$end')
    _scope_re = re.compile(r'^\$scope\s+\w+\s+(\S+)\s+\$end')
    _upscope_re = re.compile(r'^\$upscope\s+\$end')
    _enddefs_re = re.compile(r'^\$enddefinitions\s+\$end')
    _timescale_re = re.compile(r'(\d+)\s*(s|ms|us|ns|ps|fs)', re.IGNORECASE)
    _bitrange_re = re.compile(r'\s*\[\d+(?::\d+)?\]\s*$')

    in_timescale = False

    with open(vcd_path, 'r', errors='replace') as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith('$timescale'):
                in_timescale = True
                m = _timescale_re.search(stripped)
                if m:
                    timescale_fs = int(m.group(1)) * _TS_UNITS[m.group(2).lower()]
                    in_timescale = False
                continue
            if in_timescale:
                m = _timescale_re.search(stripped)
                if m:
                    timescale_fs = int(m.group(1)) * _TS_UNITS[m.group(2).lower()]
                if '$end' in stripped:
                    in_timescale = False
                continue

            m = _scope_re.match(stripped)
            if m:
                scope_stack.append(m.group(1))
                continue

            m = _upscope_re.match(stripped)
            if m:
                if scope_stack:
                    scope_stack.pop()
                continue

            m = _var_re.match(stripped)
            if m:
                reference = m.group(2)
                ref_clean = _bitrange_re.sub('', reference)
                hier_name = '.'.join(scope_stack + [ref_clean])
                signal_names.add(hier_name)
                continue

            if _enddefs_re.match(stripped):
                break

    return signal_names, timescale_fs


def _normalize_vector_value(value) -> str:
    """Normalize a pyvcd vector value to a lowercase binary string."""
    if isinstance(value, int):
        # pyvcd returns int when no x/z bits present
        return bin(value)[2:]  # e.g. 0 -> '0', 5 -> '101'
    return str(value).lower()
