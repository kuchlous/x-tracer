#!/usr/bin/env python3
"""Scan a VCD file for signals that transition to X after a given time.

Usage:
    python3 tools/find_x_signals.py --vcd <path> [--count 20] [--prefix rjn_top] [--after 1000000]

Designed for multi-GB VCD files: uses binary I/O with 8MB buffer and
stops early after finding --count X-valued signals.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

# Timescale unit to femtoseconds
_TS_UNITS = {
    's': 1_000_000_000_000_000,
    'ms': 1_000_000_000_000,
    'us': 1_000_000_000,
    'ns': 1_000_000,
    'ps': 1_000,
    'fs': 1,
}


def _fs_to_human(fs: int) -> str:
    """Convert femtoseconds to a human-readable string."""
    if fs >= 1_000_000_000_000_000:
        return f"{fs / 1_000_000_000_000_000:.3f} s"
    if fs >= 1_000_000_000_000:
        return f"{fs / 1_000_000_000_000:.3f} ms"
    if fs >= 1_000_000_000:
        return f"{fs / 1_000_000_000:.3f} us"
    if fs >= 1_000_000:
        return f"{fs / 1_000_000:.3f} ns"
    if fs >= 1_000:
        return f"{fs / 1_000:.3f} ps"
    return f"{fs} fs"


def parse_vcd_header_raw(vcd_path: Path):
    """Parse VCD header to extract id_code -> signal_name mapping and timescale.

    Returns (id_to_names, timescale_fs) where id_to_names maps id_code strings
    to lists of hierarchical signal names.

    Handles Cadence non-standard names with non-numeric brackets like
    ``signal[field_name]``.
    """
    scope_stack: list[str] = []
    id_to_names: dict[str, list[str]] = {}
    timescale_fs = 1000  # default 1ps

    _var_re = re.compile(r'^\$var\s+\w+\s+\d+\s+(\S+)\s+(.*?)\s+\$end')
    _scope_re = re.compile(r'^\$scope\s+\w+\s+(\S+)\s+\$end')
    _upscope_re = re.compile(r'^\$upscope\s+\$end')
    _enddefs_re = re.compile(r'^\$enddefinitions\s+\$end')
    _timescale_re = re.compile(r'(\d+)\s*(s|ms|us|ns|ps|fs)', re.IGNORECASE)
    _bitrange_re = re.compile(r'\s*\[\d+(?::\d+)?\]\s*$')

    in_timescale = False
    body_byte_offset = 0

    # Use binary I/O with readline() so tell() works
    with open(vcd_path, 'rb') as f:
        while True:
            raw_line = f.readline()
            if not raw_line:
                break
            line = raw_line.decode('ascii', errors='replace')
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
                id_code = m.group(1)
                reference = m.group(2)
                ref_clean = _bitrange_re.sub('', reference)
                hier_name = '.'.join(scope_stack + [ref_clean])
                if id_code not in id_to_names:
                    id_to_names[id_code] = []
                id_to_names[id_code].append(hier_name)
                continue

            if _enddefs_re.match(stripped):
                body_byte_offset = f.tell()
                break

    return id_to_names, timescale_fs, body_byte_offset


def find_x_signals(
    vcd_path: Path,
    count: int = 20,
    prefix: str | None = None,
    after: int = 0,
) -> list[dict]:
    """Scan VCD for scalar X value changes after a minimum time.

    Returns a list of dicts with keys: signal, time, time_ps, id_code.
    Stops after finding `count` distinct signals with X.
    """
    t0 = time.time()
    print(f"Parsing VCD header: {vcd_path}")
    id_to_names, timescale_fs, body_offset = parse_vcd_header_raw(vcd_path)
    t1 = time.time()

    total_signals = sum(len(v) for v in id_to_names.values())
    print(f"Header parsed in {t1 - t0:.1f}s: {total_signals} signals, "
          f"timescale = {timescale_fs} fs ({_fs_to_human(timescale_fs)}/tick)")
    print(f"Looking for X values after time {after} "
          f"({_fs_to_human(after * timescale_fs)})")

    # Filter by prefix if specified
    if prefix:
        filtered = {}
        for idc, names in id_to_names.items():
            matching = [n for n in names if n.startswith(prefix)]
            if matching:
                filtered[idc] = matching
        id_to_names = filtered
        print(f"Filtered to {sum(len(v) for v in id_to_names.values())} signals "
              f"matching prefix '{prefix}'")

    results: list[dict] = []
    seen_signals: set[str] = set()
    current_time = 0
    line_count = 0
    _PROGRESS_INTERVAL = 10_000_000

    file_size = vcd_path.stat().st_size
    print(f"Scanning value changes ({file_size / (1024**3):.2f} GB)...")

    with open(vcd_path, 'rb', buffering=8 * 1024 * 1024) as fb:
        if body_offset:
            fb.seek(body_offset)

        for raw_line in fb:
            line_count += 1
            if line_count % _PROGRESS_INTERVAL == 0:
                elapsed = time.time() - t1
                print(f"  ... {line_count // 1_000_000}M lines, "
                      f"time={current_time}, {elapsed:.0f}s elapsed, "
                      f"found {len(results)} X signals so far")

            line = raw_line.strip()
            if not line:
                continue

            first_byte = line[0]

            # Timestamp: #<digits>
            if first_byte == 35:  # '#'
                try:
                    current_time = int(line[1:])
                except ValueError:
                    pass
                continue

            # Skip directives
            if first_byte == 36:  # '$'
                continue

            # Only care about times after --after
            if current_time < after:
                continue

            # Scalar value change: x<id_code> or X<id_code>
            if first_byte in (120, 88):  # 'x', 'X'
                id_code = line[1:].decode('ascii', errors='replace')
                names = id_to_names.get(id_code)
                if names:
                    for name in names:
                        if name not in seen_signals:
                            seen_signals.add(name)
                            time_fs = current_time * timescale_fs
                            time_ps = time_fs / 1000.0
                            results.append({
                                'signal': name,
                                'time': current_time,
                                'time_ps': time_ps,
                                'time_human': _fs_to_human(time_fs),
                                'id_code': id_code,
                            })
                            if len(results) >= count:
                                break
                    if len(results) >= count:
                        break
                continue

            # Vector with x bits: b...x... <id_code>
            if first_byte in (98, 66):  # 'b', 'B'
                # Quick check: does the value portion contain 'x' or 'X'?
                space_idx = line.find(b' ')
                if space_idx == -1:
                    space_idx = line.find(b'\t')
                if space_idx > 0:
                    val_part = line[1:space_idx]
                    if b'x' in val_part or b'X' in val_part:
                        id_code = line[space_idx + 1:].decode('ascii', errors='replace')
                        names = id_to_names.get(id_code)
                        if names:
                            for name in names:
                                if name not in seen_signals:
                                    seen_signals.add(name)
                                    time_fs = current_time * timescale_fs
                                    time_ps = time_fs / 1000.0
                                    results.append({
                                        'signal': name,
                                        'time': current_time,
                                        'time_ps': time_ps,
                                        'time_human': _fs_to_human(time_fs),
                                        'id_code': id_code,
                                    })
                                    if len(results) >= count:
                                        break
                            if len(results) >= count:
                                break

    elapsed = time.time() - t0
    print(f"Scan complete in {elapsed:.1f}s: {line_count} lines, "
          f"found {len(results)} X-valued signals")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Find signals with X values in a VCD file"
    )
    parser.add_argument('--vcd', required=True, type=Path,
                        help='Path to VCD file')
    parser.add_argument('--count', type=int, default=20,
                        help='Stop after finding this many X signals (default: 20)')
    parser.add_argument('--prefix', type=str, default=None,
                        help='Only report signals matching this hierarchy prefix')
    parser.add_argument('--after', type=int, default=0,
                        help='Only report X values after this VCD time (in native units)')
    args = parser.parse_args()

    if not args.vcd.exists():
        print(f"ERROR: VCD file not found: {args.vcd}", file=sys.stderr)
        sys.exit(1)

    results = find_x_signals(args.vcd, count=args.count, prefix=args.prefix,
                             after=args.after)

    if not results:
        print("\nNo X-valued signals found after the specified time.")
        return

    # Print results table
    print(f"\n{'='*90}")
    print(f"{'#':<4} {'Signal':<55} {'Time':>12} {'Human':>12}")
    print(f"{'='*90}")
    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['signal']:<55} {r['time']:>12} {r['time_human']:>12}")
    print(f"{'='*90}")

    # Print recommended x-tracer command
    first = results[0]
    print(f"\nRecommended x-tracer command for the first signal:")
    print(f"  python3 x_tracer.py \\")
    print(f"    --vcd {args.vcd} \\")
    print(f"    --signal {first['signal']} \\")
    print(f"    --time {first['time']}")
    print()
    print("All X signals found:")
    for r in results:
        print(f"  {r['signal']}  (first X at native time {r['time']}, {r['time_human']})")


if __name__ == '__main__':
    main()
