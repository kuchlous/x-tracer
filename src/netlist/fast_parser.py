"""Fast regex-based netlist parser for flat post-P&R Verilog netlists.

Designed for Cadence Innovus output (flat netlists with 68K+ modules,
millions of cell instances). Parses line-by-line without loading the
entire file into memory.

Performance target: 480MB / 3.2M instances in <60 seconds.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from .gate import Gate, Pin
from .graph import NetlistGraph

logger = logging.getLogger(__name__)

# Progress logging interval
_PROGRESS_INTERVAL = 500_000

# --- Port direction inference (no cell library available) ---

_OUTPUT_PORTS = frozenset({
    "Y", "Z", "ZN", "Q", "QN", "Q_N", "CO", "COUT", "SUM", "S",
    "SO", "HI", "LO", "ECK",
    "Q0", "Q1", "Q2", "Q3",
})

_PG_PORTS = frozenset({
    "VDD", "VSS", "VNW", "VPW", "VDDPE", "VDDCE", "VSSE",
})

# --- Sequential detection ---
_SEQ_RE = re.compile(r"dff|flop|latch|dlat|dfxtp|dfrtp|dfsbp|dfbbp|dfstp|dlxtp|dlrtp",
                     re.IGNORECASE)

_CLOCK_PORTS = frozenset({"CLK", "CK", "clk", "ck", "clock", "CLOCK", "CLK_N", "CKN"})
_D_PORTS = frozenset({"D", "d", "DIN", "din", "DATA", "data", "D0", "D1"})
_Q_PORTS = frozenset({"Q", "q", "QN", "qn", "DOUT", "dout", "Q_N", "Q0", "Q1"})
_RESET_PORTS = frozenset({"RST", "rst", "RESET", "reset", "RESET_B", "RST_B",
                "RESET_N", "RST_N", "RN", "CLR", "clr", "CDN", "R"})
_SET_PORTS = frozenset({"SET", "set", "SET_B", "SET_N", "SN", "SDN", "PRE", "pre"})

# Fast regex to extract all .PORT(SIGNAL) connections in one findall call.
# [^()]* matches signal content without nested parens -- covers 99.9% of cases.
_PORT_CONN_RE = re.compile(r'\.(\w+)\s*\(([^()]*)\)')


def _is_sequential(cell_type: str) -> bool:
    return _SEQ_RE.search(cell_type) is not None


def _classify_ports(cell_type: str, port_names: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "clock_port": None, "d_port": None, "q_port": None,
        "reset_port": None, "set_port": None,
    }
    for name in port_names:
        if name in _CLOCK_PORTS:
            result["clock_port"] = name
        elif name in _D_PORTS:
            result["d_port"] = name
        elif name in _Q_PORTS:
            result["q_port"] = name
        elif name in _RESET_PORTS:
            result["reset_port"] = name
        elif name in _SET_PORTS:
            result["set_port"] = name
    return result


def _parse_signal_inline(sig: str, mod_prefix: str) -> Pin | None:
    """Parse signal string to Pin -- optimized for the hot path.
    mod_prefix should be module_name + '.' (precomputed).
    Uses positional args for Pin() construction.
    """
    if not sig:
        return None
    c0 = sig[0]

    if c0 == '\\':
        space_idx = sig.find(' ')
        if space_idx == -1:
            return Pin(mod_prefix + sig[1:], None)
        esc_name = sig[1:space_idx]
        remainder = sig[space_idx + 1:].lstrip()
        if remainder and remainder[0] == '[':
            close = remainder.find(']')
            if close > 1:
                try:
                    return Pin(mod_prefix + esc_name, int(remainder[1:close]))
                except ValueError:
                    pass
        return Pin(mod_prefix + esc_name, None)

    if c0.isdigit() or c0 == '{':
        return None

    bracket = sig.find('[')
    if bracket != -1:
        name = sig[:bracket].rstrip()
        close = sig.find(']', bracket + 1)
        if close != -1:
            try:
                return Pin(mod_prefix + name, int(sig[bracket + 1:close]))
            except ValueError:
                pass
        return Pin(mod_prefix + name, None)

    name = sig.rstrip()
    if name:
        return Pin(mod_prefix + name, None)
    return None


def _parse_assign(line: str, mod_prefix: str, graph_add_gate) -> None:
    """Parse: assign LHS = RHS;"""
    stripped = line[7:] if line.startswith('assign ') else line
    if stripped.endswith(';'):
        stripped = stripped[:-1]
    eq_idx = stripped.find('=')
    if eq_idx == -1:
        return
    lpin = _parse_signal_inline(stripped[:eq_idx].strip(), mod_prefix)
    rpin = _parse_signal_inline(stripped[eq_idx + 1:].strip(), mod_prefix)
    if lpin is None:
        return
    lsig = f"{lpin.signal}[{lpin.bit}]" if lpin.bit is not None else lpin.signal
    inst_path = f"__assign__{lsig}"
    g = Gate.__new__(Gate)
    g.cell_type = "assign" if rpin is not None else "assign_expr"
    g.instance_path = inst_path
    g.inputs = {"A": rpin} if rpin is not None else {}
    g.outputs = {"Y": lpin}
    g.is_sequential = False
    g.clock_port = None
    g.d_port = None
    g.q_port = None
    g.reset_port = None
    g.set_port = None
    graph_add_gate(g)


def parse_netlist_fast(
    verilog_files: list[Path] | list[str],
    top_module: str | None = None,
) -> NetlistGraph:
    """Parse flat post-P&R Verilog netlists using fast regex-based parsing.

    Single-pass line-by-line processing. Designed for Innovus output
    with 68K+ sub-modules and millions of cell instances.

    Args:
        verilog_files: Paths to Verilog source files.
        top_module: Name of the top module (unused currently, kept for API compat).

    Returns:
        A NetlistGraph with all gates and connectivity.
    """
    overall_t0 = time.time()
    graph = NetlistGraph()
    gate_count = 0

    # Local refs for hot loop -- avoids global/attribute lookups
    output_ports = _OUTPUT_PORTS
    pg_ports = _PG_PORTS
    port_conn_findall = _PORT_CONN_RE.findall
    seq_re_search = _SEQ_RE.search
    graph_add_gate = graph.add_gate_fast
    _Pin = Pin
    _Gate = Gate
    _Gate_new = Gate.__new__
    clock_ports = _CLOCK_PORTS
    d_ports = _D_PORTS
    q_ports = _Q_PORTS
    reset_ports = _RESET_PORTS
    set_ports = _SET_PORTS

    for vf in verilog_files:
        p = Path(vf)
        file_size_mb = p.stat().st_size / (1024 * 1024)
        logger.info("Fast-parsing file: %s (%.1f MB)", p, file_size_mb)

        t0 = time.time()
        current_module: str | None = None
        mod_prefix: str = ""  # module_name + "."
        accumulating = False
        accum_parts: list[str] = []

        with open(p, 'r', errors='replace', buffering=1024*1024) as f:
            for raw_line in f:
                stripped = raw_line.strip()

                if not stripped:
                    continue

                c0 = stripped[0]

                # Skip comments
                if c0 == '/' or c0 == '*':
                    continue

                # Multi-line accumulation (most common path for large netlists)
                if accumulating:
                    accum_parts.append(stripped)
                    if ';' not in stripped:
                        continue
                    accumulating = False
                    full_stmt = ' '.join(accum_parts)
                    accum_parts = []

                    # --- Inline instance processing ---
                    paren_idx = full_stmt.find('(')
                    if paren_idx == -1:
                        continue
                    prefix = full_stmt[:paren_idx]
                    sp1 = prefix.find(' ')
                    if sp1 == -1:
                        continue
                    cell_type = prefix[:sp1]
                    rest = prefix[sp1 + 1:].lstrip()
                    sp2 = rest.find(' ')
                    inst_name = rest[:sp2] if sp2 > -1 else rest
                    if not inst_name:
                        continue
                    if inst_name[0] == '\\':
                        inst_name = inst_name[1:]

                    inst_path = current_module + '.' + inst_name
                    conns = port_conn_findall(full_stmt)

                    inputs: dict[str, Pin] = {}
                    outputs: dict[str, Pin] = {}
                    is_seq = seq_re_search(cell_type) is not None
                    port_names_seq: list[str] | None = [] if is_seq else None

                    for pname, sig_str in conns:
                        if pname in pg_ports:
                            continue
                        if port_names_seq is not None:
                            port_names_seq.append(pname)
                        sig = sig_str.strip()
                        if not sig:
                            continue
                        sc = sig[0]
                        bit = None
                        if sc == '\\':
                            si = sig.find(' ')
                            if si == -1:
                                name = mod_prefix + sig[1:]
                            else:
                                esc = sig[1:si]
                                rem = sig[si + 1:].lstrip()
                                if rem and rem[0] == '[':
                                    cl = rem.find(']')
                                    if cl > 1:
                                        try:
                                            bit = int(rem[1:cl])
                                        except ValueError:
                                            pass
                                name = mod_prefix + esc
                        elif sc.isdigit() or sc == '{':
                            continue
                        else:
                            br = sig.find('[')
                            if br > -1:
                                rn = sig[:br].rstrip()
                                cl = sig.find(']', br + 1)
                                if cl > -1:
                                    try:
                                        bit = int(sig[br + 1:cl])
                                    except ValueError:
                                        pass
                                name = mod_prefix + rn
                            else:
                                name = mod_prefix + sig.rstrip()
                        pin = _Pin(name, bit)
                        if pname in output_ports:
                            outputs[pname] = pin
                        else:
                            inputs[pname] = pin

                    g = _Gate_new(_Gate)
                    g.cell_type = cell_type
                    g.instance_path = inst_path
                    g.inputs = inputs
                    g.outputs = outputs
                    g.is_sequential = is_seq
                    if is_seq and port_names_seq:
                        g.clock_port = None
                        g.d_port = None
                        g.q_port = None
                        g.reset_port = None
                        g.set_port = None
                        for nm in port_names_seq:
                            if nm in clock_ports:
                                g.clock_port = nm
                            elif nm in d_ports:
                                g.d_port = nm
                            elif nm in q_ports:
                                g.q_port = nm
                            elif nm in reset_ports:
                                g.reset_port = nm
                            elif nm in set_ports:
                                g.set_port = nm
                    else:
                        g.clock_port = None
                        g.d_port = None
                        g.q_port = None
                        g.reset_port = None
                        g.set_port = None
                    graph_add_gate(g)

                    gate_count += 1
                    if gate_count % _PROGRESS_INTERVAL == 0:
                        logger.info("  ... processed %dK gates so far",
                                    gate_count // 1000)
                    continue

                # Module boundary
                if c0 == 'm' and stripped.startswith('module '):
                    rest = stripped[7:]
                    end = 0
                    rlen = len(rest)
                    while end < rlen and rest[end] not in ' \t\n\r(;':
                        end += 1
                    current_module = rest[:end]
                    mod_prefix = current_module + '.'
                    continue

                if c0 == 'e' and stripped.startswith('endmodule'):
                    current_module = None
                    continue

                if current_module is None:
                    continue

                # Skip declarations
                if c0 in 'iowsrpl`':
                    if stripped.startswith(('input ', 'output ', 'wire ',
                                           'supply', 'reg ', 'integer ',
                                           'parameter ', 'localparam ',
                                           '`', 'specify', 'endspecify')):
                        continue

                # Handle assign
                if c0 == 'a' and stripped.startswith('assign '):
                    _parse_assign(stripped, mod_prefix, graph_add_gate)
                    continue

                # Cell instantiation
                if (c0.isalpha() or c0 == '_' or c0 == '\\') and '(' in stripped and '.' in stripped:
                    if ';' in stripped:
                        # Single-line -- inline processing (same logic as above)
                        paren_idx = stripped.find('(')
                        if paren_idx == -1:
                            continue
                        prefix = stripped[:paren_idx]
                        sp1 = prefix.find(' ')
                        if sp1 == -1:
                            continue
                        cell_type = prefix[:sp1]
                        rest = prefix[sp1 + 1:].lstrip()
                        sp2 = rest.find(' ')
                        inst_name = rest[:sp2] if sp2 > -1 else rest
                        if not inst_name:
                            continue
                        if inst_name[0] == '\\':
                            inst_name = inst_name[1:]

                        inst_path = current_module + '.' + inst_name
                        conns = port_conn_findall(stripped)

                        inputs = {}
                        outputs = {}
                        is_seq = seq_re_search(cell_type) is not None
                        port_names_seq = [] if is_seq else None

                        for pname, sig_str in conns:
                            if pname in pg_ports:
                                continue
                            if port_names_seq is not None:
                                port_names_seq.append(pname)
                            sig = sig_str.strip()
                            if not sig:
                                continue
                            sc = sig[0]
                            bit = None
                            if sc == '\\':
                                si = sig.find(' ')
                                if si == -1:
                                    name = mod_prefix + sig[1:]
                                else:
                                    esc = sig[1:si]
                                    rem = sig[si + 1:].lstrip()
                                    if rem and rem[0] == '[':
                                        cl = rem.find(']')
                                        if cl > 1:
                                            try:
                                                bit = int(rem[1:cl])
                                            except ValueError:
                                                pass
                                    name = mod_prefix + esc
                            elif sc.isdigit() or sc == '{':
                                continue
                            else:
                                br = sig.find('[')
                                if br > -1:
                                    rn = sig[:br].rstrip()
                                    cl = sig.find(']', br + 1)
                                    if cl > -1:
                                        try:
                                            bit = int(sig[br + 1:cl])
                                        except ValueError:
                                            pass
                                    name = mod_prefix + rn
                                else:
                                    name = mod_prefix + sig.rstrip()
                            pin = _Pin(name, bit)
                            if pname in output_ports:
                                outputs[pname] = pin
                            else:
                                inputs[pname] = pin

                        g = _Gate_new(_Gate)
                        g.cell_type = cell_type
                        g.instance_path = inst_path
                        g.inputs = inputs
                        g.outputs = outputs
                        g.is_sequential = is_seq
                        if is_seq and port_names_seq:
                            g.clock_port = None
                            g.d_port = None
                            g.q_port = None
                            g.reset_port = None
                            g.set_port = None
                            for nm in port_names_seq:
                                if nm in clock_ports:
                                    g.clock_port = nm
                                elif nm in d_ports:
                                    g.d_port = nm
                                elif nm in q_ports:
                                    g.q_port = nm
                                elif nm in reset_ports:
                                    g.reset_port = nm
                                elif nm in set_ports:
                                    g.set_port = nm
                        else:
                            g.clock_port = None
                            g.d_port = None
                            g.q_port = None
                            g.reset_port = None
                            g.set_port = None
                        graph_add_gate(g)

                        gate_count += 1
                        if gate_count % _PROGRESS_INTERVAL == 0:
                            logger.info("  ... processed %dK gates so far",
                                        gate_count // 1000)
                    else:
                        # Multi-line -- start accumulation
                        accumulating = True
                        accum_parts = [stripped]

        elapsed = time.time() - t0
        logger.info("  Parsed in %.1fs", elapsed)

    total_elapsed = time.time() - overall_t0
    total_gates = len(graph._gates)
    total_signals = len(graph._all_signals)
    logger.info("Fast parse complete: %d gates, %d signals in %.1fs",
                total_gates, total_signals, total_elapsed)

    return graph
