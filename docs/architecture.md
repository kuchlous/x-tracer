# X-Tracer Architecture and Implementation

## 1. Overview

X-Tracer is a backward X-value root cause tracer for gate-level simulations. It answers a single question: "Why is this signal X at this time?" by recursively walking backward through the netlist connectivity and VCD waveform data until it reaches a root cause -- an uninitialized flip-flop, an X on a primary input, an X-injected clock, an asynchronous reset stuck at X, or a multi-driver conflict.

**Inputs:**
- Flat post-place-and-route Verilog netlist (Cadence Innovus output)
- VCD waveform file (Cadence Xcelium simulation, typically with `-xprop F`)

**Output:**
- Cause tree from the query signal to one or more root causes, rendered as text, JSON, or Graphviz DOT

**Target scale:** 22nm ARM Cortex-A55 SoC
- 480 MB flat Verilog netlist, 68K+ modules, 3.2 million gate instances
- 5.5 GB VCD waveform, 28 million signals
- 22nm standard cell library (naming: `AND2_X1M_A9PP140ZTH_C30`, `DFFQNAA2W_X0P5B_A9PP140ZTH_C35`)

**User workflow:**
1. Run gate-level simulation; it fails with X on a checker output.
2. Identify the offending signal and failure time from the simulation log.
3. Run: `x-tracer -n netlist.v -v dump.vcd -s "rjn_top.u_rjn_soc_top.core.alu.result[3]" -t 450000`
4. Receive a cause tree tracing backward from the X at the output through combinational gates and sequential elements to the root cause (e.g., an uninitialized DFF in clock domain crossing logic at `rjn_soc_top.u_cdc.ff_sync_reg0`).


## 2. System Architecture

### Component Diagram

```
                        +------------------+
                        |     CLI Layer    |
                        | (src/cli/main.py)|
                        +--------+---------+
                                 |
              +------------------+------------------+
              |                  |                   |
    +---------v--------+ +------v------+  +---------v---------+
    |  Netlist Parser   | | VCD Database|  |    Gate Model     |
    | (src/netlist/     | | (src/vcd/   |  | (src/gates/       |
    |  fast_parser.py)  | |  database.py|  |  model.py,        |
    |                   | |  extract.py)|  |  cells.py,        |
    +--------+----------+ +------+------+  |  primitives.py)   |
             |                   |         +---------+---------+
             |                   |                   |
             +-------------------+-------------------+
                                 |
                        +--------v---------+
                        |   Tracer Core    |
                        | (src/tracer/     |
                        |  core.py)        |
                        +------------------+
```

### Data Flow

1. **CLI** (`src/cli/main.py`) parses command-line arguments, selects the appropriate netlist parser (fast regex vs. AST), and orchestrates the loading pipeline.

2. **Netlist Parser** (`src/netlist/fast_parser.py`) reads the flat Verilog netlist and produces a `NetlistGraph` -- a connectivity graph of `Gate` objects with `Pin` connections mapping signals to driver/fanout relationships.

3. **VCD Database** (`src/vcd/database.py`) loads signal transition data from the VCD file. The CLI computes the backward cone of signals from the query point in the netlist graph, then loads only those signals from the VCD (cone-based loading). This avoids reading the full 5.5 GB of transition data for 28M signals when only a few thousand are relevant.

4. **Tracer Core** (`src/tracer/core.py`) performs the backward DFS trace. At each signal, it looks up the driving gate in the netlist, reads input values from the VCD, evaluates the gate through the Gate Model, and recurses into the causal inputs.

5. **Gate Model** (`src/gates/model.py`) provides 4-state logic evaluation (`forward()`) and backward causality analysis (`backward_causes()`). It handles Verilog primitives, recognized standard cells (via pattern matching), and unknown cells (conservative fallback).

6. **Output Formatters** (`src/cli/formatters.py`) render the resulting `XCause` tree as indented text, JSON, or Graphviz DOT.


## 3. Netlist Parser

**File:** `src/netlist/fast_parser.py`

### Why Regex Over AST Parsing

The target netlist is a flat post-P&R Verilog file produced by Cadence Innovus. It contains 3.2 million cell instantiations across 68K modules in a 480 MB file. An AST parser (e.g., pyslang or pyverilog) would need to build a full syntax tree, which requires gigabytes of memory and minutes of parse time. The regex parser streams line-by-line with 1 MB read buffers, never holding more than one statement in memory, and completes in under 60 seconds.

The key insight is that flat Innovus netlists have an extremely regular structure: every cell instantiation follows the pattern `CELL_TYPE INSTANCE_NAME (.PORT(SIGNAL), ...);`. The regex `_PORT_CONN_RE = re.compile(r'\.(\w+)\s*\(([^()]*)\)')` extracts all port connections in a single `findall` call per statement.

### Two-Pass Processing

**Pass 1: Module Collection.** Scans all files to collect the set of defined module names. This is needed to distinguish sub-module instantiations (which create hierarchy) from leaf cell instantiations (which create gates). A line like `AND2_X1M inst0 (.A(w1), .B(w2), .Y(w3));` is a leaf cell if `AND2_X1M` is not in the defined modules set.

**Pass 2: Instance Parsing.** Parses each cell instantiation:
- Extracts cell type, instance name, and port connections
- Classifies ports as inputs or outputs using a hardcoded set `_OUTPUT_PORTS` (`Y`, `Z`, `ZN`, `Q`, `QN`, `CO`, `SUM`, etc.) and filters power/ground ports (`VDD`, `VSS`, `VNW`, `VPW`)
- Detects sequential elements via regex `_SEQ_RE` matching patterns like `dff`, `flop`, `latch`, `dlat`, `dfxtp`, `dfrtp`
- For sequential cells, classifies clock, D, Q, reset, and set ports by name matching against known port name sets

Multi-line statements (where the instantiation spans multiple lines before the closing `;`) are accumulated in a buffer before processing.

### Hierarchy Remapping via BFS

Post-P&R netlists from Innovus flatten the hierarchy but preserve module definitions. Each module's signals use the module name as a prefix (e.g., `rjn_soc_top.wire_foo`). But the VCD uses the elaborated instance path (e.g., `rjn_top.u_rjn_soc_top.wire_foo`).

The parser builds a hierarchy mapping via BFS from the top module:
1. From Pass 1 and Pass 2, it knows which modules instantiate which sub-modules
2. `_build_hierarchy_mapping()` performs BFS starting from the top module (auto-detected as the module never instantiated as a child, or specified via `--top-module`)
3. For each module, it computes the full instance path: e.g., module `rjn_soc_top` maps to path `rjn_soc_top`, its child `inst_a` of type `sub_mod_A` maps to `rjn_soc_top.inst_a`
4. `_remap_graph_hierarchy()` replaces all module-name prefixes in gate instance paths and pin signal paths with the hierarchical instance path, then rebuilds the signal maps

### Standard Cell Recognition

The parser does not need to recognize cell types -- it treats everything not in `defined_modules` as a leaf cell. Cell type recognition happens in the Gate Model layer during tracing, not during parsing.

### Signal Key Construction

Signals are represented as hierarchical dot-separated paths with optional bit indices: `rjn_soc_top.u_core.alu_result[3]`. The `Pin` dataclass stores `(signal: str, bit: int | None)`. The canonical signal key used in the graph is `"signal[bit]"` if bit is not None, or just `"signal"` for scalars. The `add_gate_fast()` method inlines this computation to avoid function call overhead on the 3.2M-instance hot path.

### Escaped Identifier Handling

Cadence netlists use Verilog escaped identifiers (`\name `) for signals with special characters. The parser strips the leading backslash and handles the trailing space delimiter. For example, `\CDN_MBIT_foo ` becomes `CDN_MBIT_foo` in the signal path.


## 4. VCD Database

**Files:** `src/vcd/database.py`, `src/vcd/extract.py`, `src/vcd/pyvcd_backend.py`, `src/vcd/pywellen_backend.py`

### Unified Query Interface

`VCDDatabase` provides a time-indexed query interface over signal transitions:

- `get_value(signal, time)` -- full value string at time (e.g., `'01x0'` for a 4-bit bus)
- `get_bit(signal, bit, time)` -- single-bit value (`'0'`, `'1'`, `'x'`; `'z'` mapped to `'x'`)
- `find_edge(signal, bit, edge, before)` -- last rising/falling edge before a time
- `first_x_time(signal, bit, after)` -- earliest time a signal becomes X
- `get_transitions(signal)` -- raw transition list for a signal
- `has_signal(signal)` -- existence check
- `ps_to_vcd(ps)` / `vcd_to_ps(vcd_time)` -- timescale conversion

Internally, transitions are stored as sorted `list[tuple[int, str]]` per signal. Lookups use `bisect_right` for O(log n) time-indexed access. Sorted time arrays are pre-extracted into `_times` dict for fast bisect operations.

### Three Backends

The VCD loading system tries three backends in order of preference:

1. **Rust streaming backend** (`xtracer_vcd.extract_signals`): A Rust extension module that streams through the VCD file once, decoding only the requested signals. Memory usage is proportional to the number of transitions in the target signals, not the file size. This is the fastest path for large VCDs (multi-GB) when loading a subset of signals.

2. **pywellen backend** (`src/vcd/pywellen_backend.py`): Uses pywellen (or xtracer_vcd's Waveform API), a Rust-backed VCD parser. It deduplicates signals by VCD identifier code, so the backend parses the VCD header separately to recover all aliases (e.g., `tb.dut.rst_n` and `tb.dut.ff0.RST_N` sharing the same VCD id code).

3. **pyvcd backend** (`src/vcd/pyvcd_backend.py`): Pure Python fallback using the pyvcd tokenizer. If the tokenizer fails (e.g., due to non-standard Cadence signal names like `signal[field_name]` with non-numeric brackets), it falls back to a hand-written line-by-line parser with binary I/O and 8 MB read buffers optimized for multi-GB files.

### PrefixMappedVCD for Hierarchy Translation

When the VCD hierarchy prefix differs from the netlist top module (common in SoC simulations where the testbench wraps the DUT), `PrefixMappedVCD` wraps the underlying `VCDDatabase` and transparently translates signal paths:

```
Netlist path:  rjn_soc_top.u_core.alu.result[3]
VCD path:      rjn_top.u_rjn_soc_top.u_core.alu.result[3]
```

The `--vcd-prefix` CLI option sets up this mapping. All tracer operations work in netlist space; `PrefixMappedVCD._to_vcd()` translates on every query by replacing the netlist top prefix with the VCD prefix.

### Cone-Based Loading

Loading all 28M signals from a 5.5 GB VCD would require tens of gigabytes of memory. The CLI implements cone-based loading:

1. **Header-only parse** (`load_vcd_header`): Reads the VCD header (up to `$enddefinitions`) to extract all signal names and the timescale. This completes in seconds even for 28M-signal VCDs because it stops before the value-change section.

2. **Backward cone computation** (`NetlistGraph.get_input_cone`): Starting from the query signal, BFS traverses the netlist graph backward through driver gates, collecting all signals reachable within `max_depth` hops. This typically yields a few thousand signals out of millions.

3. **Per-instance port signal addition**: For each gate in the cone, the CLI adds per-instance port signals (e.g., `gate.D`, `gate.Q`) that exist in the VCD. These per-instance signals are more accurate than bus-level wires in Xcelium simulations due to the bus-lag issue (see Section 5).

4. **Filtered VCD loading**: Only the cone signals (typically 1K-10K out of 28M) are loaded from the VCD. For large VCDs (>100 MB), the fast extraction path writes a temporary mini-VCD containing only the matching transitions, then loads that mini-VCD with the standard parser.

### Timescale Handling

VCD files specify a timescale (e.g., `$timescale 1 fs $end` for Cadence Xcelium at maximum resolution). The `timescale_fs` attribute stores femtoseconds per VCD time unit. The CLI accepts query times in picoseconds and converts to VCD-native units via `ps_to_vcd()`. This handles Cadence's 1 fs timescale (where 1 ps = 1000 VCD time units) as well as standard 1 ps or 1 ns timescales.


## 5. Core Tracing Algorithm

**File:** `src/tracer/core.py`

This is the heart of X-Tracer. The `trace_x()` function performs backward DFS from a query signal to root causes, producing an `XCause` tree.

### Entry Point

```python
def trace_x(netlist, vcd, gate_model, signal, bit, time, max_depth=100) -> XCause
```

Preconditions verified before tracing:
- Signal exists in VCD (`vcd.has_signal`)
- Signal is X at the query time (`vcd.get_bit`)
- Signal has drivers in the netlist (with a diagnostic error message if not, suggesting `--top-module` or `-n tb.v` if hierarchy mismatch is detected)

### Three-Color DFS (Reconvergent Fanin Prevention)

The tracer uses a three-color DFS scheme to handle reconvergent fanin -- the situation where multiple paths through the combinational logic converge on the same signal:

- **White** (unvisited): Signal has not been encountered. Proceed to trace.
- **Gray** (`exploring` set): Signal is currently on the DFS stack. Encountering it again means a true combinational cycle. Return `cause_type="cycle"`.
- **Black** (`memo` dict): Signal has been fully explored. Return the cached `XCause` immediately.

Without this scheme, reconvergent fanin causes exponential blowup. Consider a signal `Y = A & B` where both `A` and `B` are driven by a deep combinational cone sharing common inputs. Naive DFS would explore the shared cone once for `A` and again for `B`, and the problem compounds at every reconvergence point. The `memo` cache ensures each `(signal, bit, time)` triple is explored at most once.

The `exploring` set (gray nodes) is distinct from `memo` (black nodes) because a node in the `exploring` set is not yet complete -- its children are still being processed. If we encounter it again, that is a true structural cycle, not a completed result to reuse.

### Signal-Level Memoization (sig_memo)

In addition to the `(signal, bit, time)` memo, the tracer maintains a `sig_memo` keyed by `(signal, bit)` alone (without time). This allows reuse of combinational cone results across different query times.

The optimization is safe only for combinational causes -- if a signal's root cause is a sequential element (DFF), the result is time-dependent and cannot be reused. The `sig_memo` explicitly excludes `sequential_capture`, `clock_x`, `async_control_x`, and `uninit_ff` cause types.

This optimization matters because temporal backtrack (see below) can re-query the same combinational cone at a different time than the original query.

### Cause Classification: 10 Cause Types

Each `XCause` node carries a `cause_type` string indicating why the signal is X:

| Cause Type | Meaning | Leaf? |
|---|---|---|
| `primary_input` | Signal has no driver in the netlist (top-level port or unconnected wire) | Yes |
| `uninit_ff` | DFF/latch with no clock edge found, or D was not X at the last edge (uninitialized) | Yes |
| `x_injection` | Gate model predicts non-X output, but signal is X in VCD (force, deposit, or model mismatch) | Yes |
| `sequential_capture` | DFF captured an X on its D input at a clock edge | No |
| `clock_x` | Clock/enable input of a sequential element is X | No |
| `async_control_x` | Asynchronous reset or set input of a sequential element is X | No |
| `multi_driver` | Multiple gates drive the same net, and one or more produce X | No |
| `x_propagation` | Combinational gate propagates X from its causal inputs | No |
| `unknown_cell` | Cell type not recognized by the gate model; conservative trace through all X inputs | No |
| `max_depth` | Recursion depth limit reached | Yes |
| `cycle` | Structural cycle detected (gray node re-encountered) | Yes |

### _handle_sequential: DFF/Latch Tracing

Sequential element tracing follows a strict priority order:

**Priority 1: Async control X.** Check if the reset port (`CDN`, `RST`, `CLR`, `RN`, etc.) or set port (`SDN`, `SET`, `PRE`, `SN`, etc.) is X at the query time. If so, return `async_control_x` and recurse into the control signal. This takes priority because async controls override all other behavior.

**Priority 2: Clock X.** Check if the clock port (`CLK`, `CK`) is X at the query time. If so, return `clock_x` and recurse into the clock signal. An X clock means the DFF behavior is undefined.

**Priority 3: D input at last active edge.** This is the most complex case:

1. **Find the last clock edge.** `_find_last_clock_edge()` searches for the last rising edge (or falling edge for `CLK_N`/`CKN` ports) at or before the query time. The search uses `before + 1` so that edges at exactly the query time are included -- in VCD dumps, the DFF Q change and the triggering clock edge share the same timestamp.

2. **Pre-edge D sampling (T-1).** When `edge_time == time`, the VCD shows D's post-edge value (combinational outputs update at the same timestamp as the clock edge). But in real hardware, the DFF captures D from *before* the edge. The tracer samples D at `edge_time - 1` to get the pre-edge value. This breaks same-timestamp feedback loops (e.g., LFSR chains where every DFF Q and D transition simultaneously in the VCD).

3. **Multi-bit DFF D/Q matching.** Multi-bit cells like `DFFQNAA2W` have multiple D/Q pairs: `D0/QN0`, `D1/QN1`. When tracing `QN0`, the tracer matches the Q output port name suffix to find `D0` rather than the default D port. It does this by iterating over the gate's output ports to find which Q port drives the traced signal, extracting the trailing digit, and looking for `D<digit>` in the inputs.

4. **Fallback: D at query time.** If D was not X at the clock edge but Q is X, the tracer checks D at the current query time. This handles cases where the X arrived after the edge but the VCD ordering makes it appear X.

5. **Temporal backtrack.** If D is still not X, the tracer searches for when Q *first* became X using `vcd.first_x_time()`. It then finds the clock edge at or before that first-X time and checks D at that earlier edge. This handles pipeline stages where the X pulse has propagated through multiple DFFs. The search checks both the wire signal and the per-instance Q port signal (including escaped identifier forms) to find the earliest X time.

6. **Uninit fallback.** If no clock edge is found at all, or D was not X at any checked point, the tracer returns `uninit_ff` -- the flip-flop was never properly clocked with an X on D.

**Latch handling.** For latches (detected by `latch` or `dlat` in the cell type), `_find_last_transparent()` searches for the last time the enable was active (value `'1'`) rather than looking for a clock edge.

### _handle_combinational: Gate Tracing

1. **Gather input values.** For each input port of the gate, read the value from VCD at the query time, preferring the per-instance port signal (e.g., `gate.A`) over the bus-level wire signal. This is critical for Xcelium `-xprop F` simulations where bus dumps lag behind per-bit DFF Q updates.

2. **Forward check.** Evaluate the gate model's `forward()` with the gathered inputs. If the model predicts non-X output:
   - For `assign`/`buf`/`BUF` gates (pure wires): always trace through regardless, because bus-level VCD lag may show non-X on the wire while the actual signal is X.
   - For other gates: return `x_injection` -- the gate should not produce X given its inputs, so the X must come from an external source (e.g., Verilog `force`, `$deposit`, or a model limitation).

3. **Unknown cell handling.** If the gate model does not recognize the cell type, return `unknown_cell` and conservatively trace through all X-valued inputs.

4. **Backward causes.** For known cells, call `gate_model.backward_causes()` to identify which X-valued input ports are causally responsible for the X output. Recurse into each causal port. Return `x_propagation`.

### Per-Instance VCD Port Preference

Xcelium VCDs dump per-instance port signals like `rjn_top.u_soc.u_core.ff7.Q` alongside bus-level wire signals like `rjn_top.u_soc.u_core.q_bus[7]`. The per-instance signals update atomically with the gate evaluation, while bus-level signals may lag by a delta cycle.

The `_vcd_get_bit()` function implements a priority search:
1. Try `alt_signal` (per-instance port path, e.g., `gate.A`) first
2. Try escaped form (`parent.\instance.port`) for Cadence compatibility
3. Fall back to the primary wire signal

This ordering ensures the tracer sees the most accurate value even when the VCD has delta-cycle discrepancies.

### Escaped Identifier Handling

Xcelium VCDs use Verilog escaped identifiers (`\name`) for instance names with special characters (brackets, dollar signs, etc.). The netlist parser strips the backslash, so the tracer must try both forms. `_escaped_alt()` converts `a.b.CDN_MBIT_foo.D` to `a.b.\CDN_MBIT_foo.D` for VCD lookup.


## 6. Gate Model

**Files:** `src/gates/model.py`, `src/gates/cells.py`, `src/gates/primitives.py`

### 4-State Logic

All evaluation uses IEEE 1364 4-state logic: `'0'`, `'1'`, `'x'`, `'z'`. High-impedance `'z'` is normalized to `'x'` at the input of every evaluation function via `_norm()`.

Truth tables are explicit Python dicts for 2-input operations (AND2, OR2, XOR2, XNOR2), extended to N inputs by iterative application. For example, `eval_and(['x', '0', '1'])` computes `AND2[AND2['x']['0']]['1']` = `AND2['0']['1']` = `'0'`. The controlling-value property of AND (any `'0'` input forces output to `'0'` regardless of X) emerges naturally from the truth table.

### forward() -- Output Prediction

`forward(cell_type, inputs)` predicts what the gate output should be given the input values. It tries three tiers:

**Tier 1: Verilog primitives.** Handles `and`, `nand`, `or`, `nor`, `xor`, `xnor`, `not`, `buf`, `bufif0`, `bufif1`, `notif0`, `notif1`, and `assign`. Port names are `in0`, `in1`, ... or `A`, `B`, etc.

**Tier 2: Standard cell pattern matching.** `identify_cell()` strips the cell name to a base function and returns a `CellInfo` describing the cell family. Supported families:
- Basic gates: `and2`-`and8`, `nand2`-`nand4`, `or2`-`or4`, `nor2`-`nor4`, `xor2`, `xnor2`
- Complex gates: `aoi21`, `aoi22`, `aoi211`, `oai21`, `oai22`, `ao21`, `oa21` (and-or-invert, or-and-invert, and variants)
- Multiplexers: `mux2`, `mux4`
- Arithmetic: `ha` (half adder), `fa` (full adder), `maj` (majority)
- Sequential: `dff` variants, `latch` variants (evaluated conservatively -- the tracer core handles the full temporal logic)
- Utility: `inv`, `buf`, `clkbuf`, `clkinv`, `tie`, `cgen` (clock gate), `fill`/`antenna`/`endcap`

**Tier 4: Conservative fallback.** For unrecognized cells, if any input is X, output is X.

### Cell Library with Suffix Stripping

`strip_cell_name()` normalizes standard cell names to base functions:

```
AND2_X1M_A9PP140ZTH_C30   ->  and2
INV_X0P5B_A9PP140ZTH_C35  ->  inv
OAI21_X1A_A9PP140ZTH_C30  ->  oai21
DFFQNAA2W_X0P5B_A9PP140ZTH_C35  ->  dffqnaa2w  (recognized as sequential)
NAND2B_X1M_A9PP140ZTH_C30 ->  nand2  (B suffix stripped)
```

The stripping handles two naming conventions:
1. **Prefix-based** (Sky130, GF180, ASAP7): `sky130_fd_sc_hd__and2_1` strips prefix and `_1` drive suffix
2. **Suffix-based**: strips `_X<drive><type>_A<tech>_C<corner>` via regex

Inverted-input suffixes (`B`, `BB`, `XB`) are stripped after base name extraction: `NAND2B` -> `nand2b` -> `nand2`.

### backward_causes() -- Causal Input Identification

`backward_causes(cell_type, inputs)` returns the list of input port names that are X and causally responsible for the X output. This is not simply "all X inputs" -- it respects controlling values:

- **AND/NAND**: If any input is `'0'` (controlling value), the output is determined regardless of X on other inputs. Only return X ports when no input has the controlling value.
- **OR/NOR**: Same logic with controlling value `'1'`.
- **XOR/XNOR**: No controlling value -- any X input is always causal.
- **MUX2**: If select `S='0'`, only `A0` can be causal. If `S='1'`, only `A1`. If `S='x'`, both data inputs and `S` itself are causal.
- **AOI/OAI**: Decomposed into groups. For `AOI21` (Y = ~(A1&A2 | B1)): compute each group's AND/OR result, then check the outer OR/AND. Only groups that produce X contribute causal ports, and within each group, only the X-valued ports.

This precision prevents false paths. For example, tracing through an AND2 where `A='0'` and `B='x'` correctly reports no causal X inputs (the output is `'0'` regardless of B), rather than chasing B's source.


## 7. Key Design Decisions

### 1. Regex Parsing Over AST Parsing

**Problem:** A 480 MB netlist with 3.2M instances takes 10+ minutes to parse with pyslang or pyverilog, and requires 8+ GB of memory for the AST.

**Decision:** Use line-by-line regex parsing with `re.compile(r'\.(\w+)\s*\(([^()]*)\)')` for port connections.

**Trade-off:** Cannot handle complex Verilog constructs (generate blocks, parameters, expressions in port connections). This is acceptable because flat post-P&R netlists do not contain these constructs -- they are pure structural netlists with cell instantiations and assign statements.

### 2. Cone-Based VCD Loading

**Problem:** Loading 28M signals from a 5.5 GB VCD requires 30+ GB of memory and 10+ minutes.

**Decision:** Parse only the VCD header (signal names + timescale), compute the backward cone from the query signal in the netlist, map cone signals to VCD names, and load only those signals. Typically reduces the signal set from 28M to a few thousand.

**Justification:** The backward cone of a single signal through 100 depth levels of combinational logic plus a few sequential stages rarely exceeds 10K signals. The header parse takes seconds; cone computation is BFS on the netlist graph; filtered VCD loading reads the file once but only stores transitions for matching signals.

### 3. Three-Color DFS with Memoization

**Problem:** Reconvergent fanin in combinational logic causes exponential blowup. A 32-bit adder has 32 output signals that all share the same input cone. Without memoization, the tracer would re-explore the entire input cone for each output bit.

**Decision:** Use three-color DFS (white/gray/black) with a `memo` dict keyed by `(signal, bit, time)`. Gray nodes (on the DFS stack) detect cycles. Black nodes (completed) are reused instantly.

**Additional optimization:** `sig_memo` keyed by `(signal, bit)` without time, enabling reuse of combinational cone results when temporal backtrack re-queries the same cone at a different time. Explicitly excludes time-dependent sequential results.

### 4. Pre-Edge D Sampling (T-1)

**Problem:** In VCD dumps, the DFF Q change and the triggering clock edge share the same timestamp. At that timestamp, D shows its post-edge value (updated by combinational logic responding to the new Q values). But the DFF captured D's value from before the edge.

**Decision:** When `edge_time == time`, sample D at `edge_time - 1`.

**Real example:** In an LFSR chain, all DFFs have their Q, D, and CLK transitions at the same VCD timestamp (say 100). At time 100, D already shows the value driven by the downstream DFF's new Q. Sampling D at time 99 gets the pre-edge value that was actually captured.

### 5. Temporal Backtrack for Pipeline Stages

**Problem:** A DFF's Q is X at the query time, but D was not X at the last clock edge. The X was captured at an earlier clock edge and has been sitting on Q ever since (no new edge to overwrite it).

**Decision:** Find when Q first became X (`vcd.first_x_time`), locate the clock edge at or before that time, and check D at that earlier edge.

**Real example:** In a 3-stage pipeline, the X originates in stage 1 at cycle 10. By cycle 15, it has propagated to stage 3's Q. If we query stage 3's Q at cycle 15, the last clock edge might show D as non-X (stage 2's output has since been overwritten). Temporal backtrack goes back to cycle 12 (when stage 3's Q first became X) and finds D was X at that earlier edge.

### 6. Per-Instance Port Preference

**Problem:** Xcelium with `-xprop F` updates per-bit DFF Q values atomically at the gate evaluation time, but bus-level wire signals in the VCD may lag by a delta cycle. Reading the bus-level wire can show stale values.

**Decision:** Always try the per-instance port signal first (e.g., `gate_inst.A`) before falling back to the bus-level wire signal.

**Real example:** After a clock edge at time 100, `rjn_top.u_soc.ff7.Q` shows `'x'` immediately, but `rjn_top.u_soc.data_bus[7]` still shows `'1'` from the previous cycle. The tracer reads `ff7.Q` to get the correct value.

### 7. Controlling-Value Backward Analysis

**Problem:** Naive "trace all X inputs" creates false paths through gates where the X input is irrelevant due to a controlling value on another input.

**Decision:** Implement `backward_causes()` with controlling-value awareness. For AND gates, if any input is `'0'`, the output is `'0'` regardless of X on other inputs -- so no X input is causal.

**Real example:** A `NAND2_X1M` gate has `A='0'` and `B='x'`. The output is `'1'` (not X). The tracer does not follow B's source, avoiding a potentially deep and irrelevant cone exploration.

### 8. Assign Gate Passthrough

**Problem:** Continuous assign statements (`assign Y = X;`) appear as `assign`-type pseudo-gates. The gate model correctly predicts `forward(assign, {A: '0'}) = '0'`, but the signal Y might still be X in the VCD due to bus-level lag or delta-cycle issues.

**Decision:** Always trace through `assign`/`buf`/`BUF` gates regardless of the forward prediction. These are pure wires that cannot inject X, so the X must come from the driving signal.

### 9. Multi-Backend VCD Loading

**Problem:** Different VCD files have different characteristics. Cadence VCDs use non-standard signal naming. Multi-GB files need streaming I/O. Some environments lack Rust extensions.

**Decision:** Three-backend cascade: Rust streaming (fastest, lowest memory) -> pywellen (Rust-backed, handles aliases) -> pyvcd (pure Python, most tolerant of non-standard VCDs). Each backend catches exceptions and falls through to the next.

### 10. Femtosecond Internal Timescale

**Problem:** Cadence Xcelium uses `$timescale 1 fs`, meaning VCD time values are in femtoseconds. Users think in picoseconds. Other simulators use 1 ps or 1 ns.

**Decision:** Store `timescale_fs` (femtoseconds per VCD time unit) and provide `ps_to_vcd()` / `vcd_to_ps()` conversion. The CLI accepts time in picoseconds and converts internally. VCD time 450000000 at 1 fs timescale = 450000 ps = 450 ns.
