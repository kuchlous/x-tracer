# X-Tracer Semantic Specification

This document is the authoritative definition of what the X-tracer computes. It
defines root cause types, the cause tree structure, the backward tracing algorithm
with sequential element handling, and the v1 scope boundaries.

---

## 1. Problem Statement

Given:
- A gate-level netlist (post-synthesis Verilog)
- A VCD file from simulation of that netlist
- A query: `(signal[bit], time_T)` where the signal is X at time T

Produce: a **cause tree** explaining why the signal is X, rooted at the query
and terminating at **leaf causes** — the origins of the X value.

---

## 2. Definitions

### 2.1 Signal Representation

All signals are referenced at bit granularity: `signal_path[bit_index]`.
Scalars (width 1) use `signal_path[0]`. Bus-level references are never used.

### 2.2 Four-State Values

Verilog signals carry one of four values per bit: `0`, `1`, `x`, `z`.
For X-tracing purposes, `z` is treated as `x` — a high-impedance output
indicates an unresolvable state, which is an X-class problem.

### 2.3 Driver

A **driver** of a signal is a gate instance or continuous assignment whose
output port is connected to that signal in the netlist. A signal may have:
- Exactly one driver (normal case)
- Zero drivers (primary input, unconnected net)
- Multiple drivers (wired logic, tri-state bus)

### 2.4 Input Cone

The **input cone** of a signal S is the set of all signals reachable by
recursively following drivers backward through the netlist graph. The cone
is a DAG (directed acyclic graph for combinational logic) or may include
cycles through sequential elements.

---

## 3. Root Cause Types

The tracer classifies each leaf of the cause tree as one of these types:

### 3.1 `primary_input`

The signal has no driver in the netlist. It is a module port or unconnected
net. The X value was present at the design boundary.

### 3.2 `uninit_ff`

The signal is the output of a flip-flop or latch whose stored state is X,
but the D input was NOT X at the relevant clock/enable edge. This means the
sequential element was never initialized — the X is its power-on state.

### 3.3 `x_injection`

The signal is X in the VCD, but its driver's output (evaluated from the
driver's input values using X-propagation rules) would NOT be X. This
indicates the X was introduced externally (`force`, `$deposit`, or a
mechanism outside the netlist's functional model). In testcases, this is
the injection point.

### 3.4 `sequential_capture`

The signal is the output of a flip-flop that captured an X value from its
D input at a clock edge. The cause tree continues backward to the D input
at the clock edge time.

### 3.5 `clock_x`

The signal is the output of a flip-flop or latch whose clock/enable input
is X. When the clock is X, the simulator cannot determine whether an edge
occurred, so the output becomes X regardless of D. The cause tree continues
backward to the clock signal.

### 3.6 `async_control_x`

The signal is the output of a flip-flop whose asynchronous reset or set
input is X. The cause tree continues backward to the async control signal.

### 3.7 `multi_driver`

The signal has multiple drivers in the netlist, and the resolved value is X
due to contention or unresolvable resolution. The cause tree branches to
each active driver.

### 3.8 `x_propagation`

The signal is X because one or more inputs of its driving gate are X and
those X inputs are not masked by controlling values. This is an intermediate
node, not a leaf — the cause tree continues backward through the causal
inputs.

### 3.9 `unknown_cell`

The driving cell type is not recognized by the gate model. The tracer
conservatively reports all X-valued inputs as potential causes. This is a
leaf if the cell has no X inputs (the X originates inside the cell model).

---

## 4. Cause Tree Structure

### 4.1 Definition

A cause tree is a directed tree rooted at the query `(signal[bit], time)`.
Each node represents a signal that is X at a specific time. Edges point
from an X signal to the X signals that caused it (backward in the netlist
and/or time).

```python
@dataclass
class XCause:
    signal: str          # "top.dut.alu.result[3]"
    time: int            # picoseconds
    cause_type: str      # one of the types in Section 3
    gate: Gate | None    # driving gate instance (None for primary_input)
    children: list["XCause"]  # causal inputs (empty for leaf nodes)
```

### 4.2 Leaf Nodes

A leaf node has `children = []` and `cause_type` is one of:
`primary_input`, `uninit_ff`, `x_injection`, `unknown_cell`.

### 4.3 Internal Nodes

An internal node has `cause_type` of: `x_propagation`, `sequential_capture`,
`clock_x`, `async_control_x`, or `multi_driver`. Its children are the
backward-causal signals.

### 4.4 Memoization and Reconvergent Fanout

When the same `(signal, time)` pair is encountered multiple times during
backward traversal (due to reconvergent fanout), the tracer reuses the
previously computed subtree. The cause tree is logically a DAG but is
represented as a tree with shared references.

---

## 5. Backward Tracing Algorithm

### 5.1 Entry Point

```
trace(signal, bit, time) → XCause
```

Precondition: `vcd.get_bit(signal, bit, time) == 'x'`

### 5.2 Algorithm

```
function trace(signal, bit, time, visited):
    key = (signal, bit, time)
    if key in memo: return memo[key]
    if key in visited: return XCause(type="cycle", ...)
    visited.add(key)

    drivers = netlist.get_drivers(signal)

    # --- No driver ---
    if len(drivers) == 0:
        return leaf(type="primary_input")

    # --- Multiple drivers ---
    if len(drivers) > 1:
        return handle_multi_driver(signal, bit, time, drivers, visited)

    gate = drivers[0]

    # --- Sequential element ---
    if gate.type in SEQUENTIAL_TYPES:
        return handle_sequential(gate, signal, bit, time, visited)

    # --- Continuous assign ---
    if gate.type == "assign":
        return handle_assign(gate, signal, bit, time, visited)

    # --- Combinational gate ---
    return handle_combinational(gate, signal, bit, time, visited)
```

### 5.3 Sequential Element Handling

For flip-flops and latches, check causes in priority order:

```
function handle_sequential(gate, signal, bit, time, visited):
    # Priority 1: Async reset/set
    for ctrl in [gate.reset, gate.set]:
        if ctrl is not None:
            ctrl_val = vcd.get_bit(ctrl.signal, ctrl.bit, time)
            if ctrl_val == 'x':
                child = trace(ctrl.signal, ctrl.bit, time, visited)
                return XCause(type="async_control_x", children=[child])

    # Priority 2: Clock/enable is X
    clk = gate.clock  # or gate.enable for latches
    clk_val = vcd.get_bit(clk.signal, clk.bit, time)
    if clk_val == 'x':
        child = trace(clk.signal, clk.bit, time, visited)
        return XCause(type="clock_x", children=[child])

    # Priority 3: D input at last active edge
    if gate.type is DFF:
        edge_time = find_last_clock_edge(gate, vcd, before=time)
        if edge_time is None:
            return leaf(type="uninit_ff")  # no edge found
        d_val = vcd.get_bit(gate.d_input, bit, edge_time)
        if d_val == 'x':
            child = trace(gate.d_input, bit, edge_time, visited)
            return XCause(type="sequential_capture", children=[child])
        else:
            return leaf(type="uninit_ff")

    if gate.type is LATCH:
        # Find last time enable was active (high for active-high latch)
        transparent_time = find_last_transparent(gate, vcd, before=time)
        if transparent_time is None:
            return leaf(type="uninit_ff")
        d_val = vcd.get_bit(gate.d_input, bit, transparent_time)
        if d_val == 'x':
            child = trace(gate.d_input, bit, transparent_time, visited)
            return XCause(type="sequential_capture", children=[child])
        else:
            return leaf(type="uninit_ff")
```

### 5.4 Combinational Gate Handling

```
function handle_combinational(gate, signal, bit, time, visited):
    input_values = {}
    for port, sig in gate.inputs.items():
        input_values[port] = vcd.get_bit(sig.signal, sig.bit, time)

    # Check: does the gate model predict X output?
    expected_output = gate_model.forward(gate.type, input_values)
    if expected_output != 'x':
        # Driver says non-X, but signal is X → external injection
        return leaf(type="x_injection")

    # Which inputs caused the X?
    causal_ports = gate_model.backward_causes(gate.type, input_values)

    if len(causal_ports) == 0:
        # Unknown cell with X output but no X inputs
        return leaf(type="unknown_cell")

    children = []
    for port in causal_ports:
        inp = gate.inputs[port]
        child = trace(inp.signal, inp.bit, time, visited)
        children.append(child)

    return XCause(type="x_propagation", children=children)
```

### 5.5 Multi-Driver Handling

```
function handle_multi_driver(signal, bit, time, drivers, visited):
    children = []
    for gate in drivers:
        # Find the output port of this gate that drives signal
        out_val = evaluate_gate_output(gate, bit, time)
        if out_val == 'x':
            child = trace_through_gate(gate, signal, bit, time, visited)
            children.append(child)
    return XCause(type="multi_driver", children=children)
```

---

## 6. X-Propagation Rules (Gate Model)

### 6.1 Controlling Value Principle

Gates with a **controlling value** can mask X:
- AND/NAND: controlling value = 0. If any input is 0, output is known.
- OR/NOR: controlling value = 1. If any input is 1, output is known.
- XOR/XNOR: no controlling value. Any X input always produces X output.

### 6.2 backward_causes(gate_type, input_values) → list[port]

Returns the **minimal set** of input ports that are X and causally
responsible for the output being X.

**Rules:**
- **AND/NAND**: Return all ports where value is X, UNLESS any port has
  the controlling value (0), in which case output is not X and this
  function should not have been called.
- **OR/NOR**: Return all ports where value is X, UNLESS any port has
  the controlling value (1).
- **XOR/XNOR**: Return all ports where value is X.
- **BUF/NOT**: Return the input port if its value is X.
- **MUX**: If select is X, return select plus any X data input.
  If select is known, return the selected data input if it is X.

### 6.3 Complex Cells (AOI/OAI)

AND-OR-Invert (AOI) and OR-AND-Invert (OAI) cells decompose into stages:
- a21oi: `Y = ~((A1 & A2) | B1)` → AND stage (A1, A2), then OR with B1, then INV
- Apply controlling-value rules per stage

The gate model handles these by decomposing the cell function expression
into primitive operations and applying backward_causes at each stage.

### 6.4 Conservative Fallback

For cells not in the built-in model (Tier 4 / `unknown_cell`): report all
X-valued inputs as potential causes. This over-approximates (may report
non-causal inputs) but never misses a true cause.

---

## 7. Temporal Policy

### 7.1 Time of Interest

When tracing backward through a combinational gate, all inputs are
evaluated at the **same time** as the output (combinational gates have
zero logical delay for X-tracing purposes; specify timing is ignored).

### 7.2 Sequential Time Crossing

When tracing through a sequential element (DFF/latch), time shifts to the
**last active edge/transparent period** before the current time. This is
the fundamental mechanism for backward time travel in the trace.

### 7.3 X Interval

A signal may become X and then return to a known value. The tracer
operates on the X value at the query time — it does not search for the
"globally earliest" X. If the signal was X at time 100, became 0 at time
200, and became X again at time 300, a query at time 300 traces the
second X interval, not the first.

---

## 8. v1 Scope and Limitations

### 8.1 In Scope

- Verilog gate-level primitives: and, or, nand, nor, xor, xnor, not, buf
- Tri-state primitives: bufif0, bufif1, notif0, notif1
- Standard cell combinational gates (with Liberty or pattern-based model)
- DFF with optional async reset/set, sync reset, enable, scan
- Latches with optional async reset, enable
- Continuous assign statements
- Multi-driver nets (basic resolution)
- Reconvergent fanout
- Bit-level tracking through buses
- VCD and FST waveform formats

### 8.2 Out of Scope (v1)

- **Timing violations**: specify/notifier-based X generation. VCD does not
  carry timing-check event data. These Xs appear as spontaneous X
  transitions with no netlist-level explanation; the tracer will report
  them as `x_injection` (driver output doesn't predict X).
- **Strength resolution**: Verilog strength modeling (supply, strong, pull,
  weak). The tracer uses 4-state (0/1/x/z) not 8-strength semantics.
- **Delta-cycle races**: Zero-delay simulation artifacts where event
  ordering affects the result. The tracer assumes VCD values are stable
  within a timestep.
- **Hard macros / black boxes**: Opaque cells with no gate-level model.
  Reported as `unknown_cell`.
- **Power intent (UPF/CPF)**: Retention, isolation, level-shifting cells.
- **Bidirectional pads**: Inout ports with complex enable logic.
- **UDPs**: User-Defined Primitives in cell models. Treated as unknown
  cells with conservative fallback.

### 8.3 VCD Observability Boundary

The tracer operates only on signals visible in the VCD file. Simulator-
internal state (notifier registers, specify artifacts, strength
resolution intermediates) is outside the observation boundary.

Requirement: VCD must be generated with `$dumpvars(0, <top>)` to capture
the full design hierarchy. Missing signals are treated as having no
transitions (value unknown).

---

## 9. Technology Decisions

### 9.1 Netlist Parser: pyslang

Python bindings for slang (IEEE 1800-2023 SystemVerilog parser). C++
engine for parsing; single-pass Python traversal extracts connectivity
into plain dicts.

### 9.2 VCD Parser: pywellen (primary), pyvcd (fallback)

pywellen: Rust-backed multi-threaded parser (~100 MB/s). Supports VCD
and FST. Signal subset loading.

pyvcd: Pure Python streaming tokenizer. Zero dependencies. Fallback when
pywellen is not installed.

### 9.3 Graph: Plain Python dicts

```python
signal_to_drivers: dict[str, list[Gate]]  # signal → list of driving gates
gate_to_outputs: dict[str, list[str]]     # gate instance → output signals
```

### 9.4 Gate Model: Table-driven with Liberty fallback

Built-in rules for Verilog primitives and common standard cell families.
Conservative fallback (all X inputs causal) for unknown cells.
Optional Liberty (.lib) parsing for authoritative pin-function mapping.

---

## 10. Module Interfaces (Updated)

### Module 1: Netlist Parser

```python
@dataclass
class Pin:
    signal: str      # hierarchical signal path
    bit: int | None  # bit index, or None for scalar connections

@dataclass
class Gate:
    cell_type: str              # e.g. "and2", "sky130_fd_sc_hd__dfxtp_1"
    instance_path: str          # e.g. "tb.dut.U42"
    inputs: dict[str, Pin]      # port_name → Pin
    outputs: dict[str, Pin]     # port_name → Pin
    is_sequential: bool
    clock_port: str | None      # port name of clock (for DFF/latch)
    d_port: str | None          # port name of data input
    q_port: str | None          # port name of data output
    reset_port: str | None      # port name of async reset
    set_port: str | None        # port name of async set

class NetlistGraph:
    def get_drivers(self, signal: str) -> list[Gate]
    def get_fanout(self, signal: str) -> list[Gate]
    def get_gate(self, instance_path: str) -> Gate | None
    def get_all_signals(self) -> set[str]
    def get_input_cone(self, signal: str) -> set[str]
```

### Module 2: VCD Database

```python
class VCDDatabase:
    def get_value(self, signal: str, time: int) -> str
    def get_bit(self, signal: str, bit: int, time: int) -> str
    def get_transitions(self, signal: str) -> list[tuple[int, str]]
    def first_x_time(self, signal: str, bit: int, after: int = 0) -> int | None
    def find_edge(self, signal: str, bit: int, edge: str,
                  before: int) -> int | None
```

### Module 3: Gate Model

```python
class GateModel:
    def forward(self, cell_type: str,
                inputs: dict[str, str]) -> str
    def backward_causes(self, cell_type: str,
                        inputs: dict[str, str]) -> list[str]
    def is_known_cell(self, cell_type: str) -> bool
```

### Module 4: X-Tracer Core

```python
@dataclass
class XCause:
    signal: str
    time: int
    cause_type: str
    gate: Gate | None
    children: list["XCause"]

def trace_x(netlist: NetlistGraph, vcd: VCDDatabase,
            gate_model: GateModel,
            signal: str, bit: int, time: int,
            max_depth: int = 100) -> XCause
```
