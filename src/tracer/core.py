"""X-Tracer Core Algorithm — backward tracing from an X-valued signal to root causes."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

from src.netlist import NetlistGraph, Gate, Pin
from src.vcd import VCDDatabase
from src.gates import GateModel


@dataclass
class XCause:
    """A node in the X cause tree."""
    signal: str          # "tb.dut.alu.result[3]"
    time: int            # picoseconds
    cause_type: str      # primary_input, uninit_ff, x_injection,
                         # sequential_capture, clock_x, async_control_x,
                         # multi_driver, x_propagation, unknown_cell,
                         # max_depth, cycle
    gate: Optional[Gate] = None
    children: list["XCause"] = field(default_factory=list)
    top_level_port: Optional[str] = None  # for primary_input: connected top-level port


def trace_x(
    netlist: NetlistGraph,
    vcd: VCDDatabase,
    gate_model: GateModel,
    signal: str,
    bit: int,
    time: int,
    max_depth: int = 100,
) -> XCause:
    """Trace backward from signal[bit] at time to find root cause of X.

    Args:
        netlist: Parsed netlist connectivity graph.
        vcd: VCD signal database.
        gate_model: Gate X-propagation model.
        signal: Base signal path (e.g. "tb.dut.b").
        bit: Bit index (0 for scalar).
        time: Query time in picoseconds.
        max_depth: Maximum recursion depth.

    Returns:
        XCause tree rooted at the query.

    Raises:
        ValueError: If signal[bit] is not X at the given time.
    """
    # Verify precondition: signal must be in VCD
    if not vcd.has_signal(signal):
        raise ValueError(
            f"Signal '{signal}' not found in VCD"
        )

    val = _vcd_get_bit(vcd, signal, bit, time)
    if val != 'x':
        raise ValueError(
            f"Signal {signal}[{bit}] is '{val}' at time {time}, not 'x'"
        )

    # Warn if signal has no netlist coverage
    drivers = _get_drivers(netlist, signal, bit)
    sig_key = f"{signal}[{bit}]"
    if not drivers and signal not in netlist.get_all_signals() and sig_key not in netlist.get_all_signals():
        raise ValueError(
            f"Signal '{signal}' found in VCD but not in the netlist. "
            f"The netlist hierarchy may not match the VCD hierarchy. "
            f"Try including the testbench file with -n tb.v"
        )

    memo: dict[tuple[str, int, int], XCause] = {}
    sig_memo: dict[tuple[str, int], XCause] = {}
    leaf_cache: dict[tuple[str, int], list[XCause]] = {}
    exploring: set[tuple[str, int, int]] = set()

    # Deep traces (e.g. 128-DFF LFSR grid at end of simulation) can exceed
    # Python's default recursion limit.  Temporarily raise it.
    old_limit = sys.getrecursionlimit()
    needed = max_depth * 4 + 1000  # ~4 frames per trace level + headroom
    if needed > old_limit:
        sys.setrecursionlimit(needed)
    try:
        return _trace(netlist, vcd, gate_model, signal, bit, time,
                      max_depth, 0, exploring, memo, sig_memo, leaf_cache)
    finally:
        sys.setrecursionlimit(old_limit)


def _sig_key(signal: str, bit: int) -> str:
    """Format signal[bit] for display and matching."""
    return f"{signal}[{bit}]"


def _escaped_alt(sig: str) -> str | None:
    """Build escaped-identifier variant of a per-instance port signal.

    Xcelium VCDs use ``\\name`` for identifiers with special characters
    (brackets, etc.) while the netlist parser strips the backslash.
    E.g. ``a.b.CDN_MBIT_foo.D`` → ``a.b.\\CDN_MBIT_foo.D``.
    """
    parts = sig.rsplit('.', 2)
    if len(parts) >= 3:
        # parent.instance.port → parent.\instance.port
        return f"{parts[0]}.\\{parts[1]}.{parts[2]}"
    return None


def _vcd_get_bit(vcd: VCDDatabase, signal: str, bit: int, time: int,
                 alt_signal: str | None = None) -> str:
    """Safely get a bit value from VCD, returning 'x' for missing signals.

    If alt_signal is provided and exists, tries it FIRST — per-instance port
    signals (e.g. ``gate.A``) are more accurate than bus-level wire signals
    in simulators like Xcelium -xprop F, where bus dumps lag behind per-bit
    DFF Q updates.  Falls back to the primary signal.  Also tries escaped
    identifier forms for Cadence VCD compatibility.
    """
    candidates = []
    if alt_signal is not None:
        candidates.append(alt_signal)
        esc = _escaped_alt(alt_signal)
        if esc:
            candidates.append(esc)
    candidates.append(signal)
    for sig in candidates:
        try:
            val = vcd.get_bit(sig, bit, time)
        except KeyError:
            continue
        if val in ('0', '1', 'x', 'z'):
            return val
        return 'x'
    return 'x'


def _get_drivers(netlist: NetlistGraph, signal: str, bit: int) -> list[Gate]:
    """Look up drivers for a signal, trying bit-indexed key then base key."""
    # Try bit-indexed key first (e.g. "tb.dut.bus[0]")
    drivers = netlist.get_drivers(f"{signal}[{bit}]")
    if drivers:
        return drivers
    # Fall back to base signal (e.g. "tb.dut.y" for scalar)
    return netlist.get_drivers(signal)


def _trace(
    netlist: NetlistGraph,
    vcd: VCDDatabase,
    gate_model: GateModel,
    signal: str,
    bit: int,
    time: int,
    max_depth: int,
    depth: int,
    exploring: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
    leaf_cache: dict[tuple[str, int], list[XCause]] | None = None,
) -> XCause:
    """Recursive backward trace using three-color DFS.

    ``exploring`` is a global (shared) set of nodes currently on the DFS
    stack.  When a node in ``exploring`` is reached again it is a true
    cycle.  When a node in ``memo`` is reached it is a completed sub-tree
    that can be reused immediately.  This prevents the exponential blowup
    caused by reconvergent fanin re-exploring the same combinational cone.
    """
    key = (signal, bit, time)
    sig_str = _sig_key(signal, bit)

    # Black — already fully explored
    if key in memo:
        return memo[key]

    # Signal-level memoization — reuse results from a different time.
    # The netlist topology is fixed, so the same signal traced at a different
    # time produces a structurally identical cause tree (same gates, same
    # connections, same root causes).  This is critical for sequential elements:
    # without it, tracing the same DFF at every clock edge causes exponential
    # blowup on designs like LFSRs where X propagates through many cycles.
    # We attach the cached LEAF nodes directly (flattened) instead of sharing
    # the full subtree, which would cause exponential blowup during JSON
    # serialization (shared references get expanded into full copies).
    # Only reuse completed results (skip max_depth — a deeper trace may go further).
    if sig_memo is not None and leaf_cache is not None:
        sig_key = (signal, bit)
        if sig_key in sig_memo:
            prev = sig_memo[sig_key]
            if prev.cause_type != 'max_depth':
                leaves = leaf_cache.get(sig_key, [])
                node = XCause(signal=sig_str, time=time,
                              cause_type=prev.cause_type,
                              gate=prev.gate, children=leaves)
                memo[key] = node
                return node

    # Gray — currently on the DFS stack → cycle
    if key in exploring:
        return XCause(signal=sig_str, time=time, cause_type="cycle")

    # Depth limit
    if depth >= max_depth:
        return XCause(signal=sig_str, time=time, cause_type="max_depth")

    exploring.add(key)  # mark gray

    drivers = _get_drivers(netlist, signal, bit)

    # No driver → primary input
    if len(drivers) == 0:
        top_port = netlist.find_top_level_port(signal)
        node = XCause(signal=sig_str, time=time, cause_type="primary_input",
                       top_level_port=top_port)
    elif len(drivers) > 1:
        node = _handle_multi_driver(
            netlist, vcd, gate_model, signal, bit, time,
            drivers, max_depth, depth, exploring, memo, sig_memo, leaf_cache)
    elif drivers[0].is_sequential:
        node = _handle_sequential(
            netlist, vcd, gate_model, signal, bit, time,
            drivers[0], max_depth, depth, exploring, memo, sig_memo, leaf_cache)
    else:
        node = _handle_combinational(
            netlist, vcd, gate_model, signal, bit, time,
            drivers[0], max_depth, depth, exploring, memo, sig_memo, leaf_cache)

    # Mark black — remove from DFS stack, cache in memo
    exploring.discard(key)
    memo[key] = node
    if sig_memo is not None and node.cause_type != "max_depth":
        sig_key_w = (signal, bit)
        sig_memo[sig_key_w] = node
        if leaf_cache is not None:
            leaf_cache[sig_key_w] = collect_leaves(node)
    return node


def _pin_signal_bit(pin: Pin) -> tuple[str, int]:
    """Extract (signal, bit) from a Pin. Defaults bit to 0 if None."""
    if pin.bit is None:
        return (pin.signal, 0)
    # pin.bit may be a pyslang ConstantValue — convert via str for safety
    try:
        bit = int(pin.bit)
    except TypeError:
        bit = int(str(pin.bit))
    return (pin.signal, bit)


def _handle_sequential(
    netlist: NetlistGraph,
    vcd: VCDDatabase,
    gate_model: GateModel,
    signal: str,
    bit: int,
    time: int,
    gate: Gate,
    max_depth: int,
    depth: int,
    exploring: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
    leaf_cache: dict[tuple[str, int], list[XCause]] | None = None,
) -> XCause:
    """Handle sequential element (DFF/latch) tracing."""
    sig_str = _sig_key(signal, bit)

    # Priority 1: Async reset/set
    for port_name in (gate.reset_port, gate.set_port):
        if port_name is not None and port_name in gate.inputs:
            pin = gate.inputs[port_name]
            ctrl_sig, ctrl_bit = _pin_signal_bit(pin)
            alt = f"{gate.instance_path}.{port_name}"
            ctrl_val = _vcd_get_bit(vcd, ctrl_sig, ctrl_bit, time, alt_signal=alt)
            if ctrl_val == 'x':
                child = _trace(netlist, vcd, gate_model, ctrl_sig, ctrl_bit,
                               time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
                return XCause(signal=sig_str, time=time,
                              cause_type="async_control_x",
                              gate=gate, children=[child])

    # Priority 2: Clock/enable is X
    clk_port = gate.clock_port
    if clk_port is not None and clk_port in gate.inputs:
        clk_pin = gate.inputs[clk_port]
        clk_sig, clk_bit = _pin_signal_bit(clk_pin)
        alt = f"{gate.instance_path}.{clk_port}"
        clk_val = _vcd_get_bit(vcd, clk_sig, clk_bit, time, alt_signal=alt)
        if clk_val == 'x':
            child = _trace(netlist, vcd, gate_model, clk_sig, clk_bit,
                           time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
            return XCause(signal=sig_str, time=time,
                          cause_type="clock_x",
                          gate=gate, children=[child])

    # Priority 3: D input at last active edge
    # For multi-bit DFFs (e.g. DFFQNAA2W with D0/QN0, D1/QN1), match the
    # D port to the Q output being traced by suffix index.
    d_port = gate.d_port
    # Determine which Q output we're tracing
    for q_pname, q_pin in gate.outputs.items():
        q_sig_check, q_bit_check = _pin_signal_bit(q_pin)
        if q_sig_check == signal and q_bit_check == bit:
            # Found the output port — look for matching D port by index
            # e.g. QN0 → D0, Q1 → D1, QN2 → D2
            import re
            q_idx = re.search(r'(\d+)$', q_pname)
            if q_idx:
                candidate_d = f"D{q_idx.group(1)}"
                if candidate_d in gate.inputs:
                    d_port = candidate_d
            break

    if d_port is None or d_port not in gate.inputs:
        return XCause(signal=sig_str, time=time,
                      cause_type="uninit_ff", gate=gate)

    d_pin = gate.inputs[d_port]
    d_sig, d_bit = _pin_signal_bit(d_pin)

    # Determine if this is a latch or DFF
    cell_lower = gate.cell_type.lower()
    is_latch = 'latch' in cell_lower or 'dlat' in cell_lower

    if is_latch:
        edge_time = _find_last_transparent(gate, vcd, time)
    else:
        edge_time = _find_last_clock_edge(gate, vcd, time)

    if edge_time is None:
        # No clock edge found — FF was never clocked.  But if D is currently
        # X, trace through D anyway to reach root cause.
        d_alt = f"{gate.instance_path}.{d_port}"
        d_val_now = _vcd_get_bit(vcd, d_sig, d_bit, time, alt_signal=d_alt)
        if d_val_now == 'x':
            child = _trace(netlist, vcd, gate_model, d_sig, d_bit,
                           time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
            return XCause(signal=sig_str, time=time,
                          cause_type="uninit_ff",
                          gate=gate, children=[child])
        return XCause(signal=sig_str, time=time,
                      cause_type="uninit_ff", gate=gate)

    # When the clock edge is at the same time as our query, VCD shows D's
    # post-edge value (combinational outputs update at the same timestamp).
    # In real hardware, the DFF captures D from BEFORE the edge.  Sample D
    # at edge_time-1 to get the pre-edge value and trace from there.  This
    # breaks same-timestamp feedback loops (e.g. LFSR chains) where every
    # DFF Q and D transition simultaneously in the VCD.
    if edge_time == time:
        d_sample_time = edge_time - 1
    else:
        d_sample_time = edge_time

    d_alt = f"{gate.instance_path}.{d_port}"
    d_val = _vcd_get_bit(vcd, d_sig, d_bit, d_sample_time, alt_signal=d_alt)
    if d_val == 'x':
        # Temporal skip: jump to the start of the CURRENT X window on D
        # rather than walking back one clock cycle at a time.  This prevents
        # exponential blowup on designs like LFSRs where X propagates through
        # many cycles.  We use find_x_start (not first_x_time) to correctly
        # handle signals that went X → known → X: only the X window that
        # contains d_sample_time is causally relevant.
        d_trace_time = d_sample_time
        try:
            x_start = vcd.find_x_start(d_sig, d_bit, d_sample_time)
            if x_start is not None and x_start < d_sample_time:
                d_trace_time = x_start
        except KeyError:
            pass
        child = _trace(netlist, vcd, gate_model, d_sig, d_bit,
                       d_trace_time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
        return XCause(signal=sig_str, time=time,
                      cause_type="sequential_capture",
                      gate=gate, children=[child])

    # D was not X at the clock edge, but Q is X.  Before giving up, try to
    # reach root cause by:
    # 1. Checking D at the query time (X arrived after the edge)
    # 2. Finding when Q *first* became X and checking D at that earlier edge
    #    (handles pipeline stages where the X pulse has passed through)
    d_val_now = _vcd_get_bit(vcd, d_sig, d_bit, time, alt_signal=d_alt)
    if d_val_now == 'x':
        # Also temporal-skip for this path
        d_trace_time2 = time
        try:
            x_start2 = vcd.find_x_start(d_sig, d_bit, time)
            if x_start2 is not None and x_start2 < time:
                d_trace_time2 = x_start2
        except KeyError:
            pass
        child = _trace(netlist, vcd, gate_model, d_sig, d_bit,
                       d_trace_time2, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
        return XCause(signal=sig_str, time=time,
                      cause_type="sequential_capture",
                      gate=gate, children=[child])

    # Temporal backtrack: find when Q first became X and trace D at that edge.
    # The output signal may be a wire (assign output), so check both the wire
    # and the gate's Q port for the first X time.
    q_first_x = None
    for q_pname, q_pin in gate.outputs.items():
        q_sig, q_bit = _pin_signal_bit(q_pin)
        q_alt = f"{gate.instance_path}.{q_pname}"
        q_alt_esc = _escaped_alt(q_alt)
        # Try wire, per-instance port, and escaped per-instance port
        candidates_q = [(q_sig, q_bit), (q_alt, 0)]
        if q_alt_esc:
            candidates_q.append((q_alt_esc, 0))
        for try_sig, try_bit in candidates_q:
            try:
                t_x = vcd.first_x_time(try_sig, try_bit)
            except KeyError:
                continue
            if t_x is not None and (q_first_x is None or t_x < q_first_x):
                q_first_x = t_x

    if q_first_x is not None and q_first_x < time:
        # Find the clock edge at or before q_first_x
        earlier_edge = _find_last_clock_edge(gate, vcd, q_first_x)
        if earlier_edge is not None:
            if earlier_edge == q_first_x:
                earlier_d_time = earlier_edge - 1
            else:
                earlier_d_time = earlier_edge
            d_val_earlier = _vcd_get_bit(vcd, d_sig, d_bit, earlier_d_time,
                                          alt_signal=d_alt)
            if d_val_earlier == 'x':
                child = _trace(netlist, vcd, gate_model, d_sig, d_bit,
                               earlier_d_time, max_depth, depth + 1,
                               exploring, memo, sig_memo, leaf_cache)
                return XCause(signal=sig_str, time=time,
                              cause_type="sequential_capture",
                              gate=gate, children=[child])

    return XCause(signal=sig_str, time=time,
                  cause_type="uninit_ff", gate=gate)


def _find_last_clock_edge(gate: Gate, vcd: VCDDatabase, before: int) -> int | None:
    """Find the last rising clock edge at or before the given time.

    Uses ``before + 1`` so that a clock edge occurring at exactly the query
    time is included — in VCD dumps the DFF Q change and the triggering
    clock edge often share the same timestamp.
    """
    clk_port = gate.clock_port
    if clk_port is None or clk_port not in gate.inputs:
        return None
    clk_pin = gate.inputs[clk_port]
    clk_sig, clk_bit = _pin_signal_bit(clk_pin)

    # Determine edge polarity from port name
    port_upper = clk_port.upper()
    if port_upper in ('CLK_N', 'CKN'):
        edge = 'fall'
    else:
        edge = 'rise'

    # Use before+1 to include edges at exactly `before`
    try:
        return vcd.find_edge(clk_sig, clk_bit, edge, before + 1)
    except KeyError:
        # Try port-path version
        alt = f"{gate.instance_path}.{clk_port}"
        try:
            return vcd.find_edge(alt, clk_bit, edge, before + 1)
        except KeyError:
            return None


def _find_last_transparent(gate: Gate, vcd: VCDDatabase, before: int) -> int | None:
    """Find the last time the latch enable was active before the given time."""
    en_port = gate.clock_port  # For latches, clock_port holds the enable
    if en_port is None or en_port not in gate.inputs:
        return None
    en_pin = gate.inputs[en_port]
    en_sig, en_bit = _pin_signal_bit(en_pin)

    try:
        transitions = vcd.get_transitions(en_sig)
    except KeyError:
        return None

    # Walk backward to find last time enable was '1' (active-high)
    # We need the last transition to '1' before `before`
    last_active = None
    for t, val in transitions:
        if t >= before:
            break
        from src.vcd.database import _extract_bit
        bit_val = _extract_bit(val, en_bit)
        if bit_val == '1':
            last_active = t

    return last_active


def _handle_combinational(
    netlist: NetlistGraph,
    vcd: VCDDatabase,
    gate_model: GateModel,
    signal: str,
    bit: int,
    time: int,
    gate: Gate,
    max_depth: int,
    depth: int,
    exploring: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
    leaf_cache: dict[tuple[str, int], list[XCause]] | None = None,
) -> XCause:
    """Handle combinational gate / continuous assign tracing."""
    sig_str = _sig_key(signal, bit)

    # Gather input values from VCD, preferring per-instance port signals
    input_values: dict[str, str] = {}
    for port_name, pin in gate.inputs.items():
        inp_sig, inp_bit = _pin_signal_bit(pin)
        alt = f"{gate.instance_path}.{port_name}"
        input_values[port_name] = _vcd_get_bit(vcd, inp_sig, inp_bit, time,
                                                alt_signal=alt)

    # Check if gate model predicts X output
    known = gate_model.is_known_cell(gate.cell_type)
    expected = gate_model.forward(gate.cell_type, input_values)

    if expected != 'x':
        # Assign gates (pure wires) cannot inject X.  Bus-level VCD values
        # may appear non-X when per-instance port signals (on the actual
        # downstream gates) show X (Xcelium bus lag).  Always trace through.
        if gate.cell_type in ('assign', 'buf', 'BUF') and gate.inputs:
            children = []
            for port_name, pin in gate.inputs.items():
                inp_sig, inp_bit = _pin_signal_bit(pin)
                child = _trace(netlist, vcd, gate_model, inp_sig, inp_bit,
                               time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
                children.append(child)
            return XCause(signal=sig_str, time=time,
                          cause_type="x_propagation", gate=gate, children=children)
        # Driver says non-X but signal is X → external injection
        return XCause(signal=sig_str, time=time,
                      cause_type="x_injection", gate=gate)

    if not known:
        # Unknown cell — conservative: all X-valued inputs
        x_ports = [p for p, v in input_values.items() if v == 'x']
        if not x_ports:
            return XCause(signal=sig_str, time=time,
                          cause_type="unknown_cell", gate=gate)
        children = []
        for port in x_ports:
            pin = gate.inputs[port]
            inp_sig, inp_bit = _pin_signal_bit(pin)
            child = _trace(netlist, vcd, gate_model, inp_sig, inp_bit,
                           time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
            children.append(child)
        return XCause(signal=sig_str, time=time,
                      cause_type="unknown_cell", gate=gate, children=children)

    # Known cell — use backward_causes
    causal_ports = gate_model.backward_causes(gate.cell_type, input_values)

    if not causal_ports:
        # No causal ports but output is X — shouldn't happen for known cells
        # but handle gracefully
        return XCause(signal=sig_str, time=time,
                      cause_type="unknown_cell", gate=gate)

    children = []
    for port in causal_ports:
        if port not in gate.inputs:
            continue
        pin = gate.inputs[port]
        inp_sig, inp_bit = _pin_signal_bit(pin)
        child = _trace(netlist, vcd, gate_model, inp_sig, inp_bit,
                       time, max_depth, depth + 1, exploring, memo, sig_memo, leaf_cache)
        children.append(child)

    return XCause(signal=sig_str, time=time,
                  cause_type="x_propagation", gate=gate, children=children)


def _handle_multi_driver(
    netlist: NetlistGraph,
    vcd: VCDDatabase,
    gate_model: GateModel,
    signal: str,
    bit: int,
    time: int,
    drivers: list[Gate],
    max_depth: int,
    depth: int,
    exploring: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
    leaf_cache: dict[tuple[str, int], list[XCause]] | None = None,
) -> XCause:
    """Handle multi-driver net."""
    sig_str = _sig_key(signal, bit)
    children = []

    for gate in drivers:
        # Evaluate this gate's output
        input_values: dict[str, str] = {}
        for port_name, pin in gate.inputs.items():
            inp_sig, inp_bit = _pin_signal_bit(pin)
            input_values[port_name] = _vcd_get_bit(vcd, inp_sig, inp_bit, time)

        out_val = gate_model.forward(gate.cell_type, input_values)
        if out_val == 'x':
            # Trace through this gate
            child = _handle_combinational(
                netlist, vcd, gate_model, signal, bit, time,
                gate, max_depth, depth + 1, exploring, memo,
                sig_memo, leaf_cache)
            children.append(child)

    if not children:
        # All drivers produce non-X but signal is X — injection
        return XCause(signal=sig_str, time=time,
                      cause_type="x_injection")

    return XCause(signal=sig_str, time=time,
                  cause_type="multi_driver", children=children)


def collect_leaves(node: XCause) -> list[XCause]:
    """Collect all leaf nodes from a cause tree."""
    if not node.children:
        return [node]
    leaves = []
    for child in node.children:
        leaves.extend(collect_leaves(child))
    return leaves
