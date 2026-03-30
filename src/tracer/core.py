"""X-Tracer Core Algorithm — backward tracing from an X-valued signal to root causes."""

from __future__ import annotations

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
    return _trace(netlist, vcd, gate_model, signal, bit, time,
                  max_depth, 0, set(), memo, sig_memo)


def _sig_key(signal: str, bit: int) -> str:
    """Format signal[bit] for display and matching."""
    return f"{signal}[{bit}]"


def _vcd_get_bit(vcd: VCDDatabase, signal: str, bit: int, time: int,
                 alt_signal: str | None = None) -> str:
    """Safely get a bit value from VCD, returning 'x' for missing signals.

    If signal is not found and alt_signal is provided, tries alt_signal.
    Also normalizes non-4-state values to 'x' for safety.
    """
    for sig in (signal, alt_signal):
        if sig is None:
            continue
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
    visited: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
) -> XCause:
    """Recursive backward trace."""
    key = (signal, bit, time)
    sig_str = _sig_key(signal, bit)

    # Memoization — exact (signal, bit, time)
    if key in memo:
        return memo[key]

    # Signal-level memoization — reuse combinational results from a different time.
    # Only cache non-sequential causes to avoid short-circuiting DFF time boundaries.
    # This prevents exponential blowup on reconvergent combinational logic
    # while allowing the trace to cross sequential elements at different times.
    if sig_memo is not None:
        sig_key = (signal, bit)
        if sig_key in sig_memo:
            prev = sig_memo[sig_key]
            # Only reuse if the previous result was combinational (not sequential)
            if prev.cause_type not in ('sequential_capture', 'clock_x',
                                        'async_control_x', 'uninit_ff'):
                node = XCause(signal=sig_str, time=time,
                              cause_type=prev.cause_type,
                              gate=prev.gate, children=prev.children)
                memo[key] = node
                return node

    # Cycle detection
    if key in visited:
        return XCause(signal=sig_str, time=time, cause_type="cycle")

    # Depth limit
    if depth >= max_depth:
        return XCause(signal=sig_str, time=time, cause_type="max_depth")

    visited = visited | {key}  # copy-on-write to not pollute siblings

    drivers = _get_drivers(netlist, signal, bit)

    # No driver → primary input
    if len(drivers) == 0:
        node = XCause(signal=sig_str, time=time, cause_type="primary_input")
        memo[key] = node
        if sig_memo is not None and node.cause_type not in ("sequential_capture", "clock_x", "async_control_x", "uninit_ff"):
            sig_memo[(signal, bit)] = node
        return node

    # Multiple drivers → multi_driver
    if len(drivers) > 1:
        node = _handle_multi_driver(
            netlist, vcd, gate_model, signal, bit, time,
            drivers, max_depth, depth, visited, memo, sig_memo)
        memo[key] = node
        if sig_memo is not None and node.cause_type not in ("sequential_capture", "clock_x", "async_control_x", "uninit_ff"):
            sig_memo[(signal, bit)] = node
        return node

    gate = drivers[0]

    # Sequential element
    if gate.is_sequential:
        node = _handle_sequential(
            netlist, vcd, gate_model, signal, bit, time,
            gate, max_depth, depth, visited, memo, sig_memo)
        memo[key] = node
        if sig_memo is not None and node.cause_type not in ("sequential_capture", "clock_x", "async_control_x", "uninit_ff"):
            sig_memo[(signal, bit)] = node
        return node

    # Continuous assign — treat as combinational (buf)
    # Combinational gate
    node = _handle_combinational(
        netlist, vcd, gate_model, signal, bit, time,
        gate, max_depth, depth, visited, memo, sig_memo)
    memo[key] = node
    if sig_memo is not None:
        sig_memo[(signal, bit)] = node
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
    visited: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
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
                               time, max_depth, depth + 1, visited, memo, sig_memo)
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
                           time, max_depth, depth + 1, visited, memo, sig_memo)
            return XCause(signal=sig_str, time=time,
                          cause_type="clock_x",
                          gate=gate, children=[child])

    # Priority 3: D input at last active edge
    d_port = gate.d_port
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
        return XCause(signal=sig_str, time=time,
                      cause_type="uninit_ff", gate=gate)

    d_alt = f"{gate.instance_path}.{d_port}"
    d_val = _vcd_get_bit(vcd, d_sig, d_bit, edge_time, alt_signal=d_alt)
    if d_val == 'x':
        child = _trace(netlist, vcd, gate_model, d_sig, d_bit,
                       edge_time, max_depth, depth + 1, visited, memo, sig_memo)
        return XCause(signal=sig_str, time=time,
                      cause_type="sequential_capture",
                      gate=gate, children=[child])

    return XCause(signal=sig_str, time=time,
                  cause_type="uninit_ff", gate=gate)


def _find_last_clock_edge(gate: Gate, vcd: VCDDatabase, before: int) -> int | None:
    """Find the last rising clock edge before the given time."""
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

    try:
        return vcd.find_edge(clk_sig, clk_bit, edge, before)
    except KeyError:
        # Try port-path version
        alt = f"{gate.instance_path}.{clk_port}"
        try:
            return vcd.find_edge(alt, clk_bit, edge, before)
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
    visited: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
) -> XCause:
    """Handle combinational gate / continuous assign tracing."""
    sig_str = _sig_key(signal, bit)

    # Gather input values from VCD
    input_values: dict[str, str] = {}
    for port_name, pin in gate.inputs.items():
        inp_sig, inp_bit = _pin_signal_bit(pin)
        input_values[port_name] = _vcd_get_bit(vcd, inp_sig, inp_bit, time)

    # Check if gate model predicts X output
    known = gate_model.is_known_cell(gate.cell_type)
    expected = gate_model.forward(gate.cell_type, input_values)

    if expected != 'x':
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
                           time, max_depth, depth + 1, visited, memo, sig_memo)
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
                       time, max_depth, depth + 1, visited, memo, sig_memo)
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
    visited: set[tuple[str, int, int]],
    memo: dict[tuple[str, int, int], XCause],
    sig_memo: dict[tuple[str, int], XCause] | None = None,
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
                gate, max_depth, depth + 1, visited, memo)
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
