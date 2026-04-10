"""Interactive X-Tracer: step-by-step backward tracing with user control."""

from __future__ import annotations

import cmd
import sys
from dataclasses import dataclass, field

from src.netlist import NetlistGraph
from src.netlist.gate import Gate, Pin
from src.vcd import VCDDatabase
from src.gates import GateModel
from src.tracer.core import (
    _get_drivers, _vcd_get_bit, _pin_signal_bit, _sig_key,
    _find_last_clock_edge, _escaped_alt, trace_x, collect_leaves,
)


@dataclass
class TraceNode:
    """A node in the interactive trace stack."""
    signal: str
    bit: int
    time: int
    cause_type: str | None = None
    gate: Gate | None = None
    x_inputs: list[tuple[str, str, int]] = field(default_factory=list)
    # (port_name, signal_path, bit_index) for each X-valued input


def _format_value(val: str) -> str:
    """Color-format a signal value for terminal display."""
    if val == 'x':
        return '\033[91mX\033[0m'  # red
    if val == '0':
        return '0'
    if val == '1':
        return '\033[92m1\033[0m'  # green
    if val == 'z':
        return '\033[93mZ\033[0m'  # yellow
    return val


def _format_source(gate: Gate) -> str:
    """Format source file:line for a gate."""
    if gate.source_file and gate.source_line:
        return f"{gate.source_file}:{gate.source_line}"
    return "(source location unknown)"


class InteractiveTracer(cmd.Cmd):
    """Interactive step-by-step X-tracer."""

    prompt = '\033[96mxtrace>\033[0m '
    intro = None  # set in run()

    def __init__(self, netlist: NetlistGraph, vcd: VCDDatabase,
                 gate_model: GateModel, signal: str, bit: int, time: int):
        super().__init__()
        self.netlist = netlist
        self.vcd = vcd
        self.gate_model = gate_model
        self.stack: list[TraceNode] = []
        self._push(signal, bit, time)

    def _push(self, signal: str, bit: int, time: int) -> TraceNode:
        """Analyze a signal and push it onto the trace stack."""
        node = TraceNode(signal=signal, bit=bit, time=time)

        drivers = _get_drivers(self.netlist, signal, bit)

        if len(drivers) == 0:
            top_port = self.netlist.find_top_level_port(signal)
            node.cause_type = "primary_input"
            if top_port:
                node.cause_type = f"primary_input (top-level port: {top_port})"
        elif len(drivers) > 1:
            node.cause_type = "multi_driver"
            node.gate = drivers[0]
        elif drivers[0].is_sequential:
            node.cause_type = "sequential"
            node.gate = drivers[0]
        else:
            node.cause_type = "combinational"
            node.gate = drivers[0]

        # Gather X inputs if there's a driver gate
        if node.gate is not None:
            for port_name, pin in node.gate.inputs.items():
                inp_sig, inp_bit = _pin_signal_bit(pin)
                alt = f"{node.gate.instance_path}.{port_name}"
                val = _vcd_get_bit(self.vcd, inp_sig, inp_bit, time, alt_signal=alt)
                if val == 'x':
                    node.x_inputs.append((port_name, inp_sig, inp_bit))

        self.stack.append(node)
        return node

    @property
    def current(self) -> TraceNode:
        return self.stack[-1]

    def _print_node(self, node: TraceNode) -> None:
        """Print full details of the current trace node."""
        sig_str = _sig_key(node.signal, node.bit)
        val = _vcd_get_bit(self.vcd, node.signal, node.bit, node.time)
        depth = len(self.stack) - 1

        print(f"\n{'='*60}")
        print(f"  Depth:    {depth}")
        print(f"  Signal:   {sig_str}")
        print(f"  Time:     {node.time} ps")
        print(f"  Value:    {_format_value(val)}")
        print(f"  Type:     {node.cause_type}")

        if node.gate:
            g = node.gate
            print(f"  Gate:     {g.cell_type}")
            print(f"  Instance: {g.instance_path}")
            print(f"  Source:   {_format_source(g)}")

            if g.is_sequential:
                self._print_sequential_info(node)

            print(f"\n  Inputs:")
            for port_name, pin in g.inputs.items():
                inp_sig, inp_bit = _pin_signal_bit(pin)
                alt = f"{g.instance_path}.{port_name}"
                val = _vcd_get_bit(self.vcd, inp_sig, inp_bit, node.time,
                                   alt_signal=alt)
                marker = " <-- X" if val == 'x' else ""
                print(f"    {port_name:12s} = {_format_value(val)}  "
                      f"({inp_sig}[{inp_bit}]){marker}")

            print(f"  Outputs:")
            for port_name, pin in g.outputs.items():
                out_sig, out_bit = _pin_signal_bit(pin)
                alt = f"{g.instance_path}.{port_name}"
                val = _vcd_get_bit(self.vcd, out_sig, out_bit, node.time,
                                   alt_signal=alt)
                print(f"    {port_name:12s} = {_format_value(val)}  "
                      f"({out_sig}[{out_bit}])")

            if node.x_inputs:
                print(f"\n  X-valued inputs ({len(node.x_inputs)}):")
                for i, (pname, sig, bit) in enumerate(node.x_inputs):
                    print(f"    [{i}] {pname} -> {sig}[{bit}]")
            else:
                print(f"\n  No X-valued inputs")

            # Gate model evaluation
            input_values = {}
            for port_name, pin in g.inputs.items():
                inp_sig, inp_bit = _pin_signal_bit(pin)
                alt = f"{g.instance_path}.{port_name}"
                input_values[port_name] = _vcd_get_bit(
                    self.vcd, inp_sig, inp_bit, node.time, alt_signal=alt)
            expected = self.gate_model.forward(g.cell_type, input_values)
            known = self.gate_model.is_known_cell(g.cell_type)
            if known:
                causal = self.gate_model.backward_causes(g.cell_type, input_values)
                print(f"\n  Gate model: output={_format_value(expected)}, "
                      f"causal inputs={causal}")
            else:
                print(f"\n  Gate model: unknown cell '{g.cell_type}' "
                      f"(conservative: all X inputs are causal)")

        print(f"{'='*60}")

    def _print_sequential_info(self, node: TraceNode) -> None:
        """Print clock edge and D-input details for sequential elements."""
        g = node.gate
        if g.clock_port and g.clock_port in g.inputs:
            clk_pin = g.inputs[g.clock_port]
            clk_sig, clk_bit = _pin_signal_bit(clk_pin)
            alt = f"{g.instance_path}.{g.clock_port}"
            clk_val = _vcd_get_bit(self.vcd, clk_sig, clk_bit, node.time,
                                   alt_signal=alt)
            edge_time = _find_last_clock_edge(g, self.vcd, node.time)
            print(f"  Clock:    {g.clock_port} = {_format_value(clk_val)} "
                  f"({clk_sig}[{clk_bit}])")
            if edge_time is not None:
                print(f"  Last edge: t={edge_time} ps")
            else:
                print(f"  Last edge: none found")

        if g.d_port and g.d_port in g.inputs:
            d_pin = g.inputs[g.d_port]
            d_sig, d_bit = _pin_signal_bit(d_pin)
            alt = f"{g.instance_path}.{g.d_port}"
            d_val = _vcd_get_bit(self.vcd, d_sig, d_bit, node.time,
                                 alt_signal=alt)
            print(f"  D input:  {g.d_port} = {_format_value(d_val)} @ t={node.time}")
            edge_time = _find_last_clock_edge(g, self.vcd, node.time)
            if edge_time is not None:
                d_edge = edge_time - 1 if edge_time == node.time else edge_time
                d_val_edge = _vcd_get_bit(self.vcd, d_sig, d_bit, d_edge,
                                          alt_signal=alt)
                print(f"            {g.d_port} = {_format_value(d_val_edge)} "
                      f"@ t={d_edge} (pre-edge)")

    # ---- Commands ----

    def do_step(self, arg: str) -> None:
        """Step into an X-valued input. Usage: step [index]
        With no argument, auto-steps if there's exactly one X input.
        With an index, steps into that specific X input."""
        node = self.current

        if not node.x_inputs:
            print("No X-valued inputs to step into.")
            if node.cause_type and "primary_input" in node.cause_type:
                print("This is a root cause (primary input).")
            return

        if arg.strip():
            try:
                idx = int(arg.strip())
            except ValueError:
                print(f"Invalid index: {arg}")
                return
            if idx < 0 or idx >= len(node.x_inputs):
                print(f"Index out of range (0-{len(node.x_inputs)-1})")
                return
        elif len(node.x_inputs) == 1:
            idx = 0
        else:
            print(f"Multiple X inputs — specify index (0-{len(node.x_inputs)-1}):")
            for i, (pname, sig, bit) in enumerate(node.x_inputs):
                print(f"  [{i}] {pname} -> {sig}[{bit}]")
            return

        pname, sig, bit = node.x_inputs[idx]

        # For sequential elements, find appropriate trace time
        trace_time = node.time
        if node.gate and node.gate.is_sequential:
            edge_time = _find_last_clock_edge(node.gate, self.vcd, node.time)
            if edge_time is not None:
                # D port traces from clock edge; other ports from current time
                if node.gate.d_port and pname == node.gate.d_port:
                    trace_time = edge_time - 1 if edge_time == node.time else edge_time
                    # Temporal skip: jump to start of current X window
                    try:
                        x_start = self.vcd.find_x_start(sig, bit, trace_time)
                        if x_start is not None and x_start < trace_time:
                            trace_time = x_start
                    except (KeyError, AttributeError):
                        pass

        new_node = self._push(sig, bit, trace_time)
        self._print_node(new_node)

    do_s = do_step

    def do_back(self, arg: str) -> None:
        """Go back one step in the trace."""
        if len(self.stack) <= 1:
            print("Already at the starting signal.")
            return
        self.stack.pop()
        self._print_node(self.current)

    do_b = do_back

    def do_info(self, arg: str) -> None:
        """Show detailed info about the current node."""
        self._print_node(self.current)

    do_i = do_info

    def do_drivers(self, arg: str) -> None:
        """Show all drivers of the current signal (or a specified signal).
        Usage: drivers [signal]"""
        if arg.strip():
            sig = arg.strip()
            bit = 0
            import re
            m = re.match(r'^(.+)\[(\d+)\]$', sig)
            if m:
                sig, bit = m.group(1), int(m.group(2))
        else:
            sig, bit = self.current.signal, self.current.bit

        drivers = _get_drivers(self.netlist, sig, bit)
        if not drivers:
            print(f"No drivers found for {sig}[{bit}]")
            top_port = self.netlist.find_top_level_port(sig)
            if top_port:
                print(f"  -> top-level port: {top_port}")
            return

        print(f"Drivers of {sig}[{bit}] ({len(drivers)}):")
        for g in drivers:
            print(f"\n  {g.cell_type} {g.instance_path}")
            print(f"    Source: {_format_source(g)}")
            print(f"    Sequential: {g.is_sequential}")
            print(f"    Inputs:")
            for pname, pin in g.inputs.items():
                s, b = _pin_signal_bit(pin)
                val = _vcd_get_bit(self.vcd, s, b, self.current.time)
                print(f"      {pname:12s} = {_format_value(val)}  ({s}[{b}])")
            print(f"    Outputs:")
            for pname, pin in g.outputs.items():
                s, b = _pin_signal_bit(pin)
                val = _vcd_get_bit(self.vcd, s, b, self.current.time)
                print(f"      {pname:12s} = {_format_value(val)}  ({s}[{b}])")

    do_d = do_drivers

    def do_fanout(self, arg: str) -> None:
        """Show gates that read the current signal (fanout / loads).
        Usage: fanout [signal]"""
        if arg.strip():
            sig = arg.strip()
        else:
            sig = self.current.signal
            bit_sig = f"{sig}[{self.current.bit}]"
            # Try bit-indexed first
            loads = self.netlist.get_fanout(bit_sig)
            if loads:
                sig = bit_sig

        loads = self.netlist.get_fanout(sig)
        if not loads:
            # Try base signal
            loads = self.netlist.get_fanout(self.current.signal)

        if not loads:
            print(f"No fanout found for {sig}")
            return

        print(f"Fanout of {sig} ({len(loads)} loads):")
        for g in loads:
            # Find which port reads this signal
            reading_ports = []
            for pname, pin in g.inputs.items():
                if pin.signal == sig or pin.signal == self.current.signal:
                    reading_ports.append(pname)
            ports_str = ", ".join(reading_ports) if reading_ports else "?"
            print(f"  {g.cell_type} {g.instance_path} (port: {ports_str})")
            if g.source_file and g.source_line:
                print(f"    Source: {_format_source(g)}")

    do_f = do_fanout

    def do_value(self, arg: str) -> None:
        """Show signal value at current or specified time.
        Usage: value [signal] [time]"""
        parts = arg.strip().split()
        sig = self.current.signal
        bit = self.current.bit
        time = self.current.time

        if len(parts) >= 1:
            import re
            m = re.match(r'^(.+)\[(\d+)\]$', parts[0])
            if m:
                sig, bit = m.group(1), int(m.group(2))
            else:
                sig = parts[0]
                bit = 0
        if len(parts) >= 2:
            try:
                time = int(parts[1])
            except ValueError:
                print(f"Invalid time: {parts[1]}")
                return

        val = _vcd_get_bit(self.vcd, sig, bit, time)
        print(f"{sig}[{bit}] @ t={time}: {_format_value(val)}")

        # Show transitions around this time
        try:
            trans = self.vcd.get_transitions(sig)
            nearby = [(t, v) for t, v in trans if abs(t - time) <= time * 0.1 + 1000]
            if nearby:
                print(f"Nearby transitions:")
                for t, v in nearby[-10:]:
                    marker = " <-- query" if t <= time and (
                        not nearby or t == max(tt for tt, _ in nearby if tt <= time)
                    ) else ""
                    print(f"  t={t}: {v}{marker}")
        except KeyError:
            pass

    do_v = do_value

    def do_trace(self, arg: str) -> None:
        """Show the trace path so far (stack)."""
        if not self.stack:
            print("Empty trace stack")
            return
        print(f"\nTrace path ({len(self.stack)} nodes):")
        for i, node in enumerate(self.stack):
            sig_str = _sig_key(node.signal, node.bit)
            val = _vcd_get_bit(self.vcd, node.signal, node.bit, node.time)
            gate_info = ""
            if node.gate:
                gate_info = f" via {node.gate.cell_type} ({node.gate.instance_path})"
            marker = " <-- current" if i == len(self.stack) - 1 else ""
            indent = "  " * i
            print(f"  {indent}[{i}] {sig_str} = {_format_value(val)} "
                  f"@ t={node.time}{gate_info}{marker}")

    do_t = do_trace

    def do_run(self, arg: str) -> None:
        """Run the full automatic trace from the current signal.
        Usage: run [max_depth]"""
        max_depth = 100
        if arg.strip():
            try:
                max_depth = int(arg.strip())
            except ValueError:
                print(f"Invalid max_depth: {arg}")
                return

        node = self.current
        print(f"Running full trace from {node.signal}[{node.bit}] "
              f"@ t={node.time} (max_depth={max_depth})...")

        try:
            result = trace_x(self.netlist, self.vcd, self.gate_model,
                             node.signal, node.bit, node.time,
                             max_depth=max_depth)
        except ValueError as e:
            print(f"Error: {e}")
            return

        leaves = collect_leaves(result)
        types = {}
        for leaf in leaves:
            t = leaf.cause_type
            types[t] = types.get(t, 0) + 1

        print(f"\nFull trace result:")
        print(f"  Leaves: {len(leaves)}")
        print(f"  Types:  {types}")
        print(f"\nRoot causes:")
        seen = set()
        for leaf in leaves:
            key = (leaf.signal, leaf.cause_type)
            if key not in seen:
                seen.add(key)
                print(f"  [{leaf.cause_type}] {leaf.signal} @ t={leaf.time}")

    do_r = do_run

    def do_hierarchy(self, arg: str) -> None:
        """Show the signal's path through the hierarchy, tracing upward
        through driver gates to find the top-level port connection."""
        sig = arg.strip() if arg.strip() else self.current.signal
        bit = self.current.bit

        print(f"\nHierarchy trace for {sig}[{bit}]:")
        visited = set()
        current_sig = sig
        depth = 0
        max_iter = 50

        while depth < max_iter:
            if current_sig in visited:
                print(f"  {'  '*depth}(cycle detected)")
                break
            visited.add(current_sig)

            drivers = _get_drivers(self.netlist, current_sig, bit)
            indent = "  " * depth

            if not drivers:
                top_port = self.netlist.find_top_level_port(current_sig)
                if top_port:
                    print(f"  {indent}{current_sig}[{bit}] -- top-level port: {top_port}")
                else:
                    print(f"  {indent}{current_sig}[{bit}] -- no driver (primary input)")
                break

            g = drivers[0]
            # Find which output port drives this signal
            out_port = "?"
            for pname, pin in g.outputs.items():
                s, b = _pin_signal_bit(pin)
                if s == current_sig:
                    out_port = pname
                    break

            print(f"  {indent}{current_sig}[{bit}]")
            print(f"  {indent}  <- {g.cell_type} {g.instance_path} "
                  f"(port {out_port})")

            if g.is_sequential:
                print(f"  {indent}  (sequential element -- hierarchy trace stops)")
                break

            # For assigns and buffers, follow through to input
            if g.cell_type in ('assign', 'buf', 'BUF') and g.inputs:
                pin = next(iter(g.inputs.values()))
                current_sig, bit = _pin_signal_bit(pin)
                depth += 1
            else:
                # Multi-input gate -- show all inputs
                print(f"  {indent}  Inputs:")
                for pname, pin in g.inputs.items():
                    s, b = _pin_signal_bit(pin)
                    val = _vcd_get_bit(self.vcd, s, b, self.current.time)
                    print(f"  {indent}    {pname}: {s}[{b}] = {_format_value(val)}")
                break

    do_h = do_hierarchy

    def do_signals(self, arg: str) -> None:
        """Search for signals matching a pattern.
        Usage: signals <pattern>"""
        pattern = arg.strip()
        if not pattern:
            print("Usage: signals <pattern>")
            return

        import fnmatch
        all_sigs = sorted(self.netlist.get_all_signals())
        matches = [s for s in all_sigs if fnmatch.fnmatch(s, f"*{pattern}*")]

        if not matches:
            print(f"No signals matching '*{pattern}*'")
            return

        print(f"Signals matching '*{pattern}*' ({len(matches)}"
              f"{'+' if len(matches) >= 100 else ''}):")
        for s in matches[:50]:
            val = "?"
            try:
                val = _vcd_get_bit(self.vcd, s, 0, self.current.time)
            except Exception:
                pass
            print(f"  {s} = {_format_value(val)}")
        if len(matches) > 50:
            print(f"  ... and {len(matches) - 50} more")

    def do_goto(self, arg: str) -> None:
        """Jump to a different signal. Usage: goto <signal> [time]
        Signal can include bit index: goto tb.dut.foo[3] 25000"""
        parts = arg.strip().split()
        if not parts:
            print("Usage: goto <signal> [time]")
            return

        import re
        sig = parts[0]
        bit = 0
        m = re.match(r'^(.+)\[(\d+)\]$', sig)
        if m:
            sig, bit = m.group(1), int(m.group(2))

        time = self.current.time
        if len(parts) >= 2:
            try:
                time = int(parts[1])
            except ValueError:
                print(f"Invalid time: {parts[1]}")
                return

        val = _vcd_get_bit(self.vcd, sig, bit, time)
        if val != 'x':
            print(f"Warning: {sig}[{bit}] is '{val}' at t={time}, not X")

        # Start a new trace from this signal
        self.stack.clear()
        new_node = self._push(sig, bit, time)
        self._print_node(new_node)

    do_g = do_goto

    def do_time(self, arg: str) -> None:
        """Change the query time for the current signal.
        Usage: time <new_time_ps>"""
        if not arg.strip():
            print(f"Current time: {self.current.time} ps")
            return
        try:
            new_time = int(arg.strip())
        except ValueError:
            print(f"Invalid time: {arg}")
            return

        sig = self.current.signal
        bit = self.current.bit
        val = _vcd_get_bit(self.vcd, sig, bit, new_time)
        if val != 'x':
            print(f"Warning: {sig}[{bit}] is '{val}' at t={new_time}, not X")

        # Replace current node
        self.stack.pop()
        new_node = self._push(sig, bit, new_time)
        self._print_node(new_node)

    def do_quit(self, arg: str) -> bool:
        """Exit interactive mode."""
        print("Exiting interactive trace.")
        return True

    do_q = do_quit
    do_EOF = do_quit

    def do_help(self, arg: str) -> None:
        """Show available commands."""
        if arg:
            super().do_help(arg)
            return
        print("""
Interactive X-Tracer Commands:
  step [N]     (s)  Step into X input [N] (auto if only one)
  back         (b)  Go back one step
  info         (i)  Show current node details
  drivers [sig](d)  Show drivers of signal with source locations
  fanout [sig] (f)  Show loads / fanout of signal
  value [sig] [t]   (v)  Show signal value (optionally at different time)
  trace        (t)  Show the trace path so far
  run [depth]  (r)  Run full automatic trace from current point
  hierarchy [sig]   (h)  Trace signal up through hierarchy to top-level port
  signals <pat>     Search for signals matching pattern
  goto <sig> [t]    (g)  Jump to a new signal (starts fresh trace)
  time <t>          Change query time for current signal
  quit         (q)  Exit
""")

    def emptyline(self) -> None:
        """On empty input, show current node info."""
        self._print_node(self.current)

    def default(self, line: str) -> None:
        """Handle unknown commands."""
        print(f"Unknown command: '{line}'. Type 'help' for available commands.")


def run_interactive(netlist: NetlistGraph, vcd: VCDDatabase,
                    gate_model: GateModel, signal: str, bit: int,
                    time: int) -> None:
    """Launch the interactive tracer."""
    sig_str = _sig_key(signal, bit)
    val = _vcd_get_bit(vcd, signal, bit, time)

    print(f"\n\033[1mInteractive X-Tracer\033[0m")
    print(f"Query: {sig_str} = {_format_value(val)} @ t={time} ps")
    print(f"Type 'help' for commands, 'step' to trace into X inputs.\n")

    tracer = InteractiveTracer(netlist, vcd, gate_model, signal, bit, time)
    tracer._print_node(tracer.current)

    try:
        tracer.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted.")
