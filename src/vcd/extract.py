"""Fast VCD signal extraction -- extract specific signals from multi-GB VCDs in seconds.

Strategy:
1. Parse VCD header in binary mode with hand-rolled byte parsing (no regex).
   For 28M signals, this is 5-10x faster than text-mode regex.
2. Scan value-change section in binary mode with 8MB buffer.
   Only record transitions for id_codes in the target set (single set-membership check).
3. Write a mini-VCD with just the extracted signals.

Designed for 1fs timescale VCDs with 28M+ signals.
"""

from __future__ import annotations

import re
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TS_UNITS = {
    b's': 1_000_000_000_000_000,
    b'ms': 1_000_000_000_000,
    b'us': 1_000_000_000,
    b'ns': 1_000_000,
    b'ps': 1_000,
    b'fs': 1,
}

# Precompiled for the rare timescale line
_TIMESCALE_RE = re.compile(rb'(\d+)\s*(s|ms|us|ns|ps|fs)', re.IGNORECASE)
# For stripping bit ranges from references: " [7:0]" or " [3]"
_BITRANGE_RE = re.compile(rb'\s*\[\d+(?::\d+)?\]\s*$')


def _parse_header_fast(vcd_path: Path, signal_names: set[str] | None = None):
    """Parse VCD header using binary I/O -- optimized for 28M+ signal VCDs.

    Returns:
        matched_vars: list of (var_type, width, id_code, reference_raw, hier_name, scope_list)
        timescale_str: e.g. "1 fs"
        timescale_fs: int
        all_signal_names: set[str] -- all signals in VCD (only if signal_names is None;
                          otherwise empty set for speed)
        body_offset: byte offset after $enddefinitions
    """
    scope_stack: list[bytes] = []
    matched_vars: list[tuple[str, str, str, str, str, list[str]]] = []
    timescale_str = "1 fs"
    timescale_fs = 1
    body_offset = 0
    signal_count = 0

    # If we only need specific signals, we can skip building all_signal_names
    collect_all = signal_names is None
    all_signal_names: set[str] = set()

    # Convert signal_names to bytes for fast matching if provided
    signal_names_bytes: set[bytes] | None = None
    if signal_names is not None:
        signal_names_bytes = {s.encode('ascii', errors='replace') for s in signal_names}

    # Byte constants
    _VAR = b'$var'
    _SCOPE = b'$scope'
    _UPSCOPE = b'$upscope'
    _ENDDEFS = b'$enddefinitions'
    _TIMESCALE = b'$timescale'
    _END = b'$end'
    _DOT = ord('.')

    in_timescale = False

    with open(vcd_path, 'rb', buffering=8 * 1024 * 1024) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            # Fast first-byte check: most header lines start with '$'
            if line[0] != 36:  # not '$'
                # Could be timescale value on its own line
                if in_timescale:
                    m = _TIMESCALE_RE.search(line)
                    if m:
                        val = int(m.group(1))
                        unit = m.group(2).lower()
                        timescale_fs = val * _TS_UNITS[unit]
                        timescale_str = f"{val} {unit.decode('ascii')}"
                    if b'$end' in line:
                        in_timescale = False
                continue

            # $var lines are the vast majority (28M of them)
            if line.startswith(_VAR):
                signal_count += 1

                # Fast hand-parsing: $var <type> <width> <id_code> <reference> $end
                # Split only what we need
                # Find fields by splitting on whitespace
                # Format: "$var wire 1 h SWDIOTMS $end"
                #          0    1    2 3 4...     -1
                parts = line.split()
                # parts: [b'$var', b'wire', b'1', b'h', b'SWDIOTMS', b'$end']
                # or:    [b'$var', b'wire', b'1', b'h', b'SWDIOTMS', b'[7:0]', b'$end']
                if len(parts) < 6:
                    continue

                id_code = parts[3]
                # Reference is everything between id_code and $end
                # Find $end index
                end_idx = len(parts) - 1
                while end_idx > 3 and parts[end_idx] != _END:
                    end_idx -= 1
                ref_parts = parts[4:end_idx]
                reference_raw = b' '.join(ref_parts)

                # Strip bit range: " [7:0]" -> ""
                ref_clean = _BITRANGE_RE.sub(b'', reference_raw)

                # Build hierarchical name using bytes
                if scope_stack:
                    hier_name_b = b'.'.join(scope_stack) + b'.' + ref_clean
                else:
                    hier_name_b = ref_clean

                if collect_all:
                    hier_str = hier_name_b.decode('ascii', errors='replace')
                    all_signal_names.add(hier_str)

                # Check if this signal is in our target set
                if signal_names_bytes is None or hier_name_b in signal_names_bytes:
                    var_type = parts[1].decode('ascii', errors='replace')
                    width = parts[2].decode('ascii', errors='replace')
                    id_str = id_code.decode('ascii', errors='replace')
                    ref_str = reference_raw.decode('ascii', errors='replace')
                    hier_str = hier_name_b.decode('ascii', errors='replace')
                    scope_strs = [s.decode('ascii', errors='replace') for s in scope_stack]
                    matched_vars.append((var_type, width, id_str, ref_str,
                                        hier_str, scope_strs))
                continue

            if line.startswith(_SCOPE):
                # $scope module <name> $end
                parts = line.split()
                if len(parts) >= 3:
                    scope_stack.append(parts[2])
                continue

            if line.startswith(_UPSCOPE):
                if scope_stack:
                    scope_stack.pop()
                continue

            if line.startswith(_ENDDEFS):
                body_offset = f.tell()
                break

            if line.startswith(_TIMESCALE):
                in_timescale = True
                m = _TIMESCALE_RE.search(line)
                if m:
                    val = int(m.group(1))
                    unit = m.group(2).lower()
                    timescale_fs = val * _TS_UNITS[unit]
                    timescale_str = f"{val} {unit.decode('ascii')}"
                    in_timescale = False
                continue

    logger.info("Header: %d signals parsed, %d matched", signal_count, len(matched_vars))
    return matched_vars, timescale_str, timescale_fs, all_signal_names, body_offset


def extract_signals(vcd_path: Path, signal_names: set[str], output_path: Path) -> None:
    """Extract specified signals from a large VCD into a smaller VCD file.

    Optimized for multi-GB VCDs: parses header to find id_code mappings,
    then scans value-change section keeping only transitions for target codes.
    Writes a valid mini-VCD with proper header and only the extracted signals.

    Args:
        vcd_path: Path to input VCD file.
        signal_names: Set of hierarchical signal names to extract
                      (e.g. {'rjn_top.u_rjn_soc_top.SWDIOTMS'}).
        output_path: Path to write the extracted mini-VCD.
    """
    t0 = time.monotonic()
    vcd_path = Path(vcd_path)
    output_path = Path(output_path)

    # Phase 1: Parse header to find id_codes for requested signals
    # Pass signal_names so we skip building 28M-entry all_signal_names set
    logger.info("Parsing VCD header for signal extraction ...")
    matched_vars, timescale_str, timescale_fs, _, body_offset = \
        _parse_header_fast(vcd_path, signal_names)

    t_header = time.monotonic() - t0
    logger.info("Header parsed in %.1fs", t_header)

    # Build the set of target id_codes (bytes for fast comparison)
    target_codes: set[str] = set()
    id_to_names: dict[str, list[str]] = {}
    for var_type, width, id_code, ref_raw, hier_name, scopes in matched_vars:
        target_codes.add(id_code)
        if id_code not in id_to_names:
            id_to_names[id_code] = []
        id_to_names[id_code].append(hier_name)

    found = {v[4] for v in matched_vars}
    missing = signal_names - found
    if missing:
        logger.warning("Signals not found in VCD: %s", missing)
    if not target_codes:
        logger.warning("No matching signals found; writing empty VCD.")

    logger.info("Found %d signal(s) mapped to %d id_code(s)",
                len(found), len(target_codes))

    # Build target_codes as encoded bytes for fast lookup
    target_codes_bytes: set[bytes] = {c.encode('ascii') for c in target_codes}

    # Phase 2: Write mini-VCD header
    with open(output_path, 'w') as out:
        out.write("$date extracted $end\n")
        out.write("$version x-tracer extract $end\n")
        out.write(f"$timescale {timescale_str} $end\n")
        out.write("\n")

        # Write scope/var declarations for matched signals
        scopes_written: list[str] = []
        for var_type, width, id_code, ref_raw, hier_name, scope_list in matched_vars:
            # Navigate to correct scope
            common = 0
            for i in range(min(len(scopes_written), len(scope_list))):
                if scopes_written[i] == scope_list[i]:
                    common = i + 1
                else:
                    break
            # Close scopes that diverge
            for _ in range(len(scopes_written) - common):
                out.write("$upscope $end\n")
                scopes_written.pop()
            # Open new scopes
            for s in scope_list[common:]:
                out.write(f"$scope module {s} $end\n")
                scopes_written.append(s)
            out.write(f"$var {var_type} {width} {id_code} {ref_raw} $end\n")

        # Close remaining scopes
        for _ in scopes_written:
            out.write("$upscope $end\n")

        out.write("$enddefinitions $end\n")

    # Phase 3: Scan value-change section, append matching transitions
    _PROGRESS_INTERVAL = 50_000_000
    line_count = 0
    written_count = 0
    file_size = vcd_path.stat().st_size

    with open(output_path, 'ab') as out:
        with open(vcd_path, 'rb', buffering=8 * 1024 * 1024) as fb:
            if body_offset:
                fb.seek(body_offset)

            current_time_line: bytes | None = None
            time_written = False

            for raw_line in fb:
                line_count += 1

                if line_count % _PROGRESS_INTERVAL == 0:
                    elapsed = time.monotonic() - t0
                    pct = (fb.tell() / file_size * 100) if file_size else 0
                    logger.info("  ... %dM lines, %.0f%% of file, %.1fs elapsed",
                                line_count // 1_000_000, pct, elapsed)

                line = raw_line.strip()
                if not line:
                    continue

                first_byte = line[0]

                # Timestamp: #<digits>
                if first_byte == 35:  # '#'
                    current_time_line = line
                    time_written = False
                    continue

                # Skip $ directives ($dumpvars, $end, etc.)
                if first_byte == 36:  # '$'
                    if line.startswith(b'$dumpvars') or line == b'$end':
                        out.write(raw_line)
                    continue

                # Scalar: <value><id_code>  (value is one of 0,1,x,X,z,Z)
                if first_byte in (48, 49, 120, 88, 122, 90):
                    id_bytes = line[1:]
                    if id_bytes in target_codes_bytes:
                        if current_time_line is not None and not time_written:
                            out.write(current_time_line + b'\n')
                            time_written = True
                        out.write(raw_line)
                        written_count += 1
                    continue

                # Vector: b/B/r/R <value> <id_code>
                if first_byte in (98, 66, 114, 82):
                    space_idx = line.find(b' ')
                    if space_idx == -1:
                        space_idx = line.find(b'\t')
                    if space_idx > 0:
                        id_bytes = line[space_idx + 1:]
                        if id_bytes in target_codes_bytes:
                            if current_time_line is not None and not time_written:
                                out.write(current_time_line + b'\n')
                                time_written = True
                            out.write(raw_line)
                            written_count += 1
                    continue

    elapsed = time.monotonic() - t0
    out_size = output_path.stat().st_size
    logger.info("Extraction complete: %d transitions written in %.1fs "
                "(%.1f MB/s, output: %.1f KB)",
                written_count, elapsed,
                file_size / (1024 * 1024 * elapsed) if elapsed > 0 else 0,
                out_size / 1024)


def load_vcd_fast(vcd_path: Path, signals: set[str],
                  all_signal_names: set[str] | None = None,
                  timescale_fs: int | None = None) -> 'VCDDatabase':
    """Load specific signals from a large VCD efficiently using extract_signals.

    Extracts the requested signals into a temporary mini-VCD, then loads
    that mini-VCD with the standard parser. This avoids the overhead of
    full tokenization on multi-GB files.

    For VCDs with 28M+ signals, the fast binary header parser finds target
    id_codes in ~30s (vs ~160s with regex), then the value-change scan
    writes only matching transitions.

    Args:
        vcd_path: Path to the (potentially large) VCD file.
        signals: Set of hierarchical signal names to load.
        all_signal_names: Pre-parsed set of all signal names (avoids re-parsing
                          the 28M-signal header). If None, will be parsed from the VCD.
        timescale_fs: Pre-parsed timescale in femtoseconds. If None, parsed from VCD.

    Returns:
        VCDDatabase containing only the requested signals.
    """
    import tempfile
    from .database import VCDDatabase

    vcd_path = Path(vcd_path)
    t0 = time.monotonic()

    # Extract to a temp file in the same directory (avoids cross-fs copy)
    try:
        tmp_dir = vcd_path.parent
        with tempfile.NamedTemporaryFile(suffix='.vcd', delete=False,
                                          dir=tmp_dir) as tmp:
            tmp_path = Path(tmp.name)
    except OSError:
        # Fall back to system temp if VCD dir is read-only
        import tempfile as _tf
        with _tf.NamedTemporaryFile(suffix='.vcd', delete=False) as tmp:
            tmp_path = Path(tmp.name)

    try:
        extract_signals(vcd_path, signals, tmp_path)

        # Load the small extracted VCD with the standard parser
        from .pyvcd_backend import load as _load_pyvcd
        db = _load_pyvcd(tmp_path, signals)

        # Get full signal list if not provided (needed for has_signal on non-extracted signals)
        if all_signal_names is None or timescale_fs is None:
            logger.info("Parsing full signal list from header ...")
            _, _, ts_fs, all_sigs, _ = _parse_header_fast(vcd_path)
            if all_signal_names is None:
                all_signal_names = all_sigs
            if timescale_fs is None:
                timescale_fs = ts_fs

        result = VCDDatabase(
            db._transitions,
            all_signal_names,
            timescale_fs=timescale_fs,
        )

        elapsed = time.monotonic() - t0
        logger.info("load_vcd_fast: loaded %d signals in %.1fs", len(signals), elapsed)
        return result
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
