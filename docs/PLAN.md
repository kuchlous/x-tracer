# X-Tracer for Verilog Gate-Level Netlists — Implementation Plan

## Problem Summary

Given:
- A set of Verilog gate-level netlist files
- A VCD (Value Change Dump) file
- A full hierarchical signal path (e.g. `top.core.alu.result[3]`)
- A time T at which the signal is X

The tool traces backward through time and the input cone to find the **root cause** of the X.

---

## Technology Stack

| Component | Library | Rationale |
|-----------|---------|-----------|
| Verilog parsing | `pyslang` | Best-in-class parser, full SV/Verilog support, Python bindings |
| VCD parsing | `vcdvcd` (streaming mode) | Streaming + binary search indexing avoids loading GBs into RAM |
| Signal time lookup | `bisect` (stdlib) on sorted `numpy` arrays | O(log n) lookup, compact memory |
| Graph representation | Plain Python dicts + `igraph` for traversal | Avoids C++ build complexity; igraph is 10–50x faster than NetworkX |
| CLI | `click` | Standard, clean |

No existing open-source X-tracer exists. We build on the above primitives.

---

## Architecture: 5 Independent Modules

```
x-tracer/
├── src/
│   ├── netlist/       # Module 1 — Netlist Parser & Graph
│   ├── vcd/           # Module 2 — VCD Signal Database
│   ├── gates/         # Module 3 — Gate X-Propagation Model
│   ├── tracer/        # Module 4 — X-Tracer Core Algorithm
│   └── cli/           # Module 5 — CLI & Reporting
├── tests/
│   └── data/          # Sample netlists and VCDs for testing
└── pyproject.toml
```

---

## Module 1: Netlist Parser & Graph Builder (`src/netlist/`)

**Objective:** Parse Verilog gate-level netlists into a queryable graph.

**Interface (what other modules consume):**
```python
class NetlistGraph:
    def get_driver(self, signal_path: str) -> Gate | None
    def get_gate(self, instance_path: str) -> Gate | None
    def get_fanout(self, signal_path: str) -> list[Gate]

@dataclass
class Gate:
    type: str            # "and", "or", "DFF_X1", etc.
    instance_path: str   # full hierarchical path
    inputs: dict[str, str]   # port_name -> signal_path
    outputs: dict[str, str]  # port_name -> signal_path

def parse_netlist(verilog_files: list[Path]) -> NetlistGraph: ...
```

**Implementation details:**
- Use `pyslang` to parse and elaborate the netlist
- Walk the instance hierarchy; flatten to a two-level map: `signal_path → driving_gate`
- Handle standard primitives: `and`, `or`, `nand`, `nor`, `xor`, `xnor`, `not`, `buf`, `bufif0/1`
- Handle standard cell instantiations by matching cell name patterns (e.g. `AND2_X1`)
- Handle `assign` statements as pass-through gates
- Store as plain Python dicts (memory-compact, fast lookup)

**Deliverable:** `parse_netlist()` + `NetlistGraph` class with 100% test coverage on sample netlists.

---

## Module 2: VCD Signal Database (`src/vcd/`)

**Objective:** Efficiently answer "what was signal S's value at time T?" for any T.

**Interface:**
```python
class VCDDatabase:
    def get_value(self, signal_path: str, time: int) -> str  # '0','1','x','z'
    def get_x_onset(self, signal_path: str, before_time: int) -> int | None
    def get_transitions(self, signal_path: str) -> list[tuple[int, str]]

def load_vcd(vcd_path: Path, signals: set[str] | None = None) -> VCDDatabase: ...
```

**Implementation details:**
- Stream VCD via `vcdvcd` callbacks (`store_tvs=False`) to avoid loading entire file
- Build per-signal: `times: np.ndarray[int64]`, `values: list[str]` (parallel arrays)
- `get_value(signal, T)` = `bisect_right(times, T) - 1` → O(log n)
- `get_x_onset(signal, T)` = search backward from T for last transition to 'x'
- `signals` filter: only store signals in the backward cone (lazily populated)
- Support VCD scopes → hierarchical signal name mapping

**Deliverable:** `VCDDatabase` with streaming load, O(log n) queries, and optional signal filtering.

---

## Module 3: Gate X-Propagation Model (`src/gates/`)

**Objective:** Given a gate type and its input values, determine (a) the output value, and (b) which inputs *caused* the output to be X (backward analysis).

**Interface:**
```python
class GateModel:
    def forward(self, gate_type: str, inputs: dict[str, str]) -> str
    def backward_causes(
        self, gate_type: str, inputs: dict[str, str], output_port: str
    ) -> list[str]   # list of input port names that caused the X output

def get_gate_model(gate_type: str) -> GateModel: ...
```

**X-propagation rules (examples):**

| Gate | Output is X when... | Causal inputs |
|------|---------------------|---------------|
| AND | any input is X (and no 0 present) | all X inputs |
| AND | input is X with all others 1 | that X input |
| OR | any input is X (and no 1 present) | all X inputs |
| NOT/BUF | input is X | the input |
| XOR | any input is X | all X inputs |
| DFF | D is X at clock edge, or async reset is X | D, or reset |

**Implementation details:**
- Pure Python, no dependencies — fully unit-testable in isolation
- Support all standard Verilog primitives and common standard cell name patterns
- Handle multi-bit (bus) signals: per-bit X propagation
- For `DFF`/`LATCH`: capture semantics (D→Q on clock edge, enable, reset priority)
- Configurable standard cell library mapping (`NAND2_X1` → `nand`, etc.)

**Deliverable:** Full gate library with forward + backward X-propagation for all primitive types and common standard cell patterns.

---

## Module 4: X-Tracer Core Algorithm (`src/tracer/`)

**Objective:** Backward traversal from `(signal, time)` through the netlist + VCD to find root causes.

**Interface:**
```python
@dataclass
class XCause:
    type: str   # "uninit_ff", "primary_input", "x_input", "x_propagation"
    signal: str
    time: int
    gate: Gate | None
    children: list["XCause"]   # what caused this

def trace_x(
    netlist: NetlistGraph,
    vcd: VCDDatabase,
    signal_path: str,
    time: int,
    max_depth: int = 100,
) -> XCause: ...
```

**Algorithm:**
```
trace(signal, time):
  value = vcd.get_value(signal, time)
  assert value == 'x'

  gate = netlist.get_driver(signal)

  if gate is None:
    # primary input or undriven wire
    return XCause(type="primary_input", ...)

  if gate.type in SEQUENTIAL_TYPES:  # DFF, LATCH
    # find the clock edge just before `time`
    clk_edge_time = find_last_clock_edge(gate, vcd, before=time)
    d_value = vcd.get_value(gate.inputs["D"], clk_edge_time)
    if d_value == 'x':
      return trace(gate.inputs["D"], clk_edge_time)
    else:
      # X came from reset or initialization
      return XCause(type="uninit_ff", ...)

  # Combinational gate
  input_values = {p: vcd.get_value(s, time) for p, s in gate.inputs.items()}
  causal_ports = gate_model.backward_causes(gate.type, input_values, output_port)

  children = []
  for port in causal_ports:
    input_signal = gate.inputs[port]
    # Time regression: when did this input become X?
    x_onset = vcd.get_x_onset(input_signal, before_time=time)
    t = x_onset if x_onset is not None else time
    children.append(trace(input_signal, t))

  return XCause(type="x_propagation", gate=gate, children=children)
```

**Implementation details:**
- Memoize `(signal, time)` pairs to avoid re-tracing shared paths
- Cycle detection via visited set (for combinational loops — guard anyway)
- `max_depth` cutoff with a warning
- Parallel exploration of sibling causes using `concurrent.futures`

**Deliverable:** `trace_x()` with memoization, cycle detection, and async-ready design.

---

## Module 5: CLI & Reporting (`src/cli/`)

**Objective:** Entry point + output formatting.

**Usage:**
```bash
x-tracer \
  --netlist top.v cells.v \
  --vcd simulation.vcd \
  --signal "top.core.alu.result[3]" \
  --time 12345000 \
  [--format text|json|dot] \
  [--max-depth 50]
```

**Output formats:**
- `text`: indented tree of cause chain
- `json`: full `XCause` tree serialized
- `dot`: Graphviz DOT for visualization

**Deliverable:** CLI entry point + all 3 output formats.

---

## Agent Work Assignment

| Agent | Module | Dependencies | Can start immediately? |
|-------|--------|-------------|----------------------|
| Agent A | Module 1 (Netlist Parser) | pyslang | Yes |
| Agent B | Module 2 (VCD Database) | vcdvcd, numpy | Yes |
| Agent C | Module 3 (Gate Model) | none | Yes |
| Agent D | Module 4 (X-Tracer Core) | Modules 1, 2, 3 | After A, B, C |
| Agent E | Module 5 (CLI) | Module 4 | After D |

Agents A, B, C can work **fully in parallel**.

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Netlist parse (1M gates) | < 30s |
| VCD load (1GB, filtered to cone) | < 60s |
| Trace depth 50, 10K signals in cone | < 5s |
| Peak RSS | < 2GB for above |

---

## Suggested Implementation Order

1. Build testcase corpus and validation harness — see [TESTCASE_GENERATION.md](TESTCASE_GENERATION.md)
2. Create project scaffold with `pyproject.toml`, module stubs, and interface definitions
3. Launch Agents A, B, C in parallel on their modules
4. Integrate with Agent D once A/B/C have passing unit tests
5. Wire up CLI with Agent E

---

## Testcase Corpus

Testcase generation is a separate workstream documented in [TESTCASE_GENERATION.md](TESTCASE_GENERATION.md). It covers:
- Open-source netlist sources (ISCAS, ITC'99, PicoRV32, Ibex, EPFL, SkyWater)
- Explicit X injection strategy (`force` / `$deposit`)
- Testbench auto-generation and wrapping for downloaded netlists
- Signal hierarchy scanner for injection target selection
- Runtime capping for existing testbenches
- 5-layer validation pipeline

## Open-Source Netlist Sources for Testcase Coverage

### Tier 1: Ready to use (already gate-level Verilog)

**ISCAS'85 / ISCAS'89** — highest priority starting point
- ISCAS'85: pure combinational, 5–2600 gates — ideal for gate model (Module 3) validation
- ISCAS'89: sequential with DFFs, up to 250K gates — ideal for flop/latch X-tracing
- **Key advantage:** correct answers are published in academic fault analysis literature — cross-check tracer output without manually constructing expected results
- Sources: `github.com/jpsety/verilog_benchmark_circuits`, `github.com/santoshsmalagi/Benchmarks`

**ITC'99** — medium scale, already synthesized with Synopsys DC
- 29–70K gates, both combinational and sequential variants
- Synthesized gate-level netlists included — no extra synthesis step
- Source: `github.com/cad-polito-it/I99T`, CC licensed

**HDL Benchmarks (TrustworthyComputing)** — RTL + Yosys-synthesized netlists paired
- Fast to onboard; netlists already generated
- Source: `github.com/TrustworthyComputing/hdl-benchmarks`

---

### Tier 2: Synthesize from RTL (requires a Yosys step)

**PicoRV32** (~8–15K gates) — best RISC-V option for realistic sequential X cases
- Has a comprehensive test suite → VCD generation straightforward
- Synthesize: `yosys -p "synth -top picorv32; write_verilog netlist.v" picorv32.v`
- License: ISC — `github.com/YosysHQ/picorv32`

**Ibex** (~12–20K gates) — formally verified, well-characterized sequential logic
- Good for validating the tracer handles real-world sequential complexity
- License: Apache 2.0 — `github.com/lowRISC/ibex`

**CVA6** (~50–100K gates) — largest open RISC-V core, good performance stress test
- License: Solderpad — `github.com/openhwgroup/cva6`

**EPFL Benchmarks** — arithmetic circuits up to 1M+ gates
- Multiplier, sqrt, adder — ideal for the `stress/` testcase category
- Source: `github.com/lsils/benchmarks`

---

### Tier 3: Real tapeout netlists (SkyWater 130nm)

**Caravel / SkyWater PDK designs**
- Uses `sky130_fd_sc_hd__*` standard cells — validates that cell library mapping in Module 3 handles real vendor cell names
- Generated by OpenLane/Yosys — realistic tool-output format
- Source: `github.com/efabless/caravel`, Apache 2.0

---

### Mapping to Coverage Matrix

| Agent | Category | Recommended Source |
|-------|----------|--------------------|
| Agent A (combinational) | `and_x_prop`, `or_masking`, `reconvergent` | ISCAS'85 (c17, c432, c880) |
| Agent B (sequential) | `flop_uninit`, `latch_enable_x`, `reset_x` | ISCAS'89 (s27, s386, s1423), ITC'99 |
| Agent C (structural) | `undriven_net`, `black_box`, `multi_driver` | ITC'99 edge cases, hand-authored |
| Agent D (stress) | `deep_cone`, `large_synthetic` | EPFL multiplier, CVA6, PicoRV32 |
| Correctness agent | Golden regression suite | ISCAS'85 (cross-check against published fault analysis) |

### VCD Generation

For all Tier 2 sources: use Icarus Verilog (`iverilog`) with each repo's existing testbenches. See [TESTCASE_GENERATION.md](TESTCASE_GENERATION.md) for the full testbench handling, signal scanner, and validation pipeline.
