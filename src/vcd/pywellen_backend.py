"""VCD loading backend using pywellen (Rust-backed, fast)."""

from __future__ import annotations

from pathlib import Path

import pywellen

from .database import VCDDatabase


def load(vcd_path: Path, signals: set[str] | None = None) -> VCDDatabase:
    """Load VCD using pywellen and return a VCDDatabase.

    pywellen deduplicates VCD signals by identifier code, returning only
    one name per code. To recover all aliases (e.g., tb.dut.rst_n and
    tb.dut.ff0.RST_N sharing the same code), we fall back to parsing the
    VCD header ourselves and creating alias entries in the transition map.
    """
    w = pywellen.Waveform(str(vcd_path))
    h = w.hierarchy

    # Collect all vars and their full names (deduplicated by pywellen)
    all_vars: list[tuple[str, pywellen.Var]] = []
    for var in h.all_vars():
        full_name = var.full_name(h)
        all_vars.append((full_name, var))

    # Parse VCD header to find ALL signal names and their id codes
    # This recovers aliases that pywellen deduplicates
    id_to_names, all_signal_names = _parse_vcd_header(vcd_path)

    # Build var lookup by name for pywellen vars
    name_to_var = {name: var for name, var in all_vars}

    # Filter to requested signals if specified
    if signals is not None:
        names_to_load = signals & all_signal_names
    else:
        names_to_load = all_signal_names

    # Determine which id_codes we need to load
    if signals is not None:
        # Find which codes correspond to requested signals
        needed_codes: set[str] = set()
        for id_code, code_names in id_to_names.items():
            if any(n in signals for n in code_names):
                needed_codes.add(id_code)
    else:
        needed_codes = set(id_to_names.keys())

    # Build code -> pywellen var mapping
    name_to_var = {name: var for name, var in all_vars}
    code_to_var: dict[str, pywellen.Var] = {}
    for id_code, code_names in id_to_names.items():
        for cn in code_names:
            if cn in name_to_var:
                code_to_var[id_code] = name_to_var[cn]
                break

    # Load transitions only for needed codes
    transitions: dict[str, list[tuple[int, str]]] = {}
    for id_code in needed_codes:
        var = code_to_var.get(id_code)
        if var is None:
            continue
        sig = w.get_signal(var)
        changes = list(sig.all_changes())
        tlist: list[tuple[int, str]] = []
        for time, val in changes:
            tlist.append((time, _normalize_value(val)))

        # Add all aliases for this code (if no filter, add all; if filtered,
        # add all aliases — they share the same data and cost nothing)
        for name in id_to_names[id_code]:
            if signals is None or name in names_to_load:
                transitions[name] = tlist

    return VCDDatabase(transitions, all_signal_names)


def _parse_vcd_header(vcd_path: Path) -> tuple[dict[str, list[str]], set[str]]:
    """Parse VCD header to extract all signal names and id code mappings.

    Returns:
        id_to_names: dict mapping id_code -> list of hierarchical signal names
        all_names: set of all signal names
    """
    import re
    id_to_names: dict[str, list[str]] = {}
    all_names: set[str] = set()
    scope_stack: list[str] = []

    with open(vcd_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('$scope'):
                parts = line.split()
                if len(parts) >= 3:
                    scope_stack.append(parts[2])
            elif line.startswith('$upscope'):
                if scope_stack:
                    scope_stack.pop()
            elif line.startswith('$var'):
                parts = line.split()
                # $var type width id_code name [range] $end
                if len(parts) >= 5:
                    id_code = parts[3]
                    sig_name = parts[4]
                    full_path = '.'.join(scope_stack + [sig_name])
                    all_names.add(full_path)
                    id_to_names.setdefault(id_code, []).append(full_path)
            elif line.startswith('$enddefinitions'):
                break

    return id_to_names, all_names


def _normalize_value(val) -> str:
    """Normalize a pywellen value to a string."""
    if isinstance(val, int):
        # Single-bit integer: 0 or 1
        return str(val)
    # Already a string like 'x', 'z', or a binary vector
    return str(val).lower()
