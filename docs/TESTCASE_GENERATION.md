# X-Tracer Testcase Generation Plan

## Motivation

### Why testcases first

X-tracing semantics are subtle. The correct answer for a given query depends on gate-level
X-propagation rules, sequential capture timing, reconvergent fanout, and the interaction of
all three. Bugs in the tracer's logic are easy to introduce and hard to spot by code review
alone — a wrong answer looks plausible.

Building the testcase corpus before the tracer implementation means:
- Every module is developed against a concrete pass/fail signal from day one
- Regressions are caught immediately as modules are integrated
- Agents working on the tracer have unambiguous ground truth to code against, not just a
  spec document

Without this, the risk is that the tracer is "working" against hand-waved examples and only
fails on real designs when it is much harder to debug.

### Why explicit X injection

The naive approach to generating testcases is to simulate a design, find a signal that
happens to be X in the VCD, and then derive the expected root cause by tracing through the
netlist manually or with a reference simulator. This has two serious problems:

1. **Deriving the expected answer is as hard as writing the tracer itself.** A reference
   simulator that correctly handles all gate types, sequential elements, UDPs, and
   multi-driver resolution is a substantial project in its own right — effectively building
   the tool twice.

2. **X can arise from many simultaneous sources** in a real simulation (uninitialized
   registers, undriven inputs, simulator pessimism), making the "correct" root cause
   ambiguous and the expected answer difficult to specify precisely.

Explicit X injection avoids both problems. By ensuring the simulation environment is
completely clean before injection — all inputs driven, all registers initialized — the
injection point is by construction the root cause of every X observed in the VCD, including
cases with reconvergent fanout where multiple paths from the injection point converge on the
query signal. The expected answer is always the injection point; the corpus can be built and
graded without any reference simulator.

### Why synthetic tests

Open-source netlists provide realistic structural complexity but offer no guarantee that
any specific gate type, propagation scenario, or structural pattern is present. A corpus
built only from downloaded netlists may miss entire classes of tracer bugs — for example,
a bug in XOR X-propagation will never be caught if no ISCAS benchmark happens to exercise
a two-input XOR with exactly one X input under the chosen stimulus.

Synthetic netlists are programmatically generated to guarantee exact coverage of:
- Every primitive gate type with every relevant combination of X and non-X inputs
- Masking cases: AND with a 0 masking X; OR with a 1 masking X
- Carry chains of configurable bit width (the counter example)
- Reconvergent fanout at exact depths
- FF chains of configurable depth
- Mux trees with X on select vs. X on data

### Why open-source netlists

Synthetic tests guarantee coverage of known scenarios but cannot cover what we don't think
to generate. Open-source netlists from the ISCAS benchmark suite, RISC-V cores, and
SkyWater tapeouts provide realistic structural complexity: deep reconvergent cones,
mixed cell libraries, legal Verilog constructs, and sequential interactions that arise only
in real designs.

The ISCAS'85 benchmarks have the additional advantage that their topology is extensively
characterized in the literature, providing confidence that the netlist structure (fanout,
cone depth, reconvergence) is as expected. Note: published ISCAS fault analysis results
(stuck-at ATPG, observability, controllability) are a different fault model from Verilog
X-propagation and cannot be used to cross-check testcase correctness.

---

## Core Principle: Explicit X Injection

The only source of X in any automated testcase simulation is an explicitly injected X via
`force` on a primary input or `$deposit` on an RTL-level `reg` state element. This means:

- Any signal that is X in the VCD at or after injection time is in the forward cone of the
  injection point
- The injection point is by construction the root cause of every X in the simulation —
  including in reconvergent fanout cases where multiple paths from the injection point
  converge on the query signal
- The tracer is expected to trace all paths back to the injection point; stopping at an
  intermediate signal is a tracer bug, not an accepted answer
- No reference simulator is required for automated testcases

---

## Tracer Evaluation Oracle

This section defines the oracle used to grade tracer outputs against the corpus. This
definition is authoritative; no separate semantics document is required for automated
testcases.

### Cone membership

Static netlist traversal cannot correctly define the cone for sequential circuits. Which
flip-flops actually capture and propagate X depends on when clock edges occur relative to
the injection time — a fact determined by simulation, not by netlist structure alone. A
flip-flop is in the static cone of the injection point but may never carry X because its
capturing clock edge fired before the injection, or because its enable was low.

`cone_members` is therefore computed dynamically from the VCD after simulation, at
**bit level**. Bus-level membership is insufficient: consider a counter where `count[0]`
goes X first due to an X carry-in, then `count[1]` goes X one cycle later through carry
propagation, and `count[7]` only goes X several cycles after that. Bus-level tracking
collapses all bits of `count` to a single entry and loses the causal ordering — the tracer
must know that `count[0]` went X first and is the root cause, not `count[7]`.

Every `(signal, bit)` pair is tracked independently:

```python
cone_members = set()
for sig in vcd.all_signals():
    width = vcd.get_width(sig)
    for bit in range(width):
        if vcd.get_first_x_time(sig, bit, after=injection_time) is not None:
            cone_members.add(f"{sig}[{bit}]")
```

Scalars (width = 1) are represented as `sig[0]` internally. The canonical string form for
all cone members and all tracer outputs is `signal[bit]` — e.g., `tb.dut.count[0]`,
`tb.dut.result[3]`.

This is correct for both combinational and sequential circuits:
- **Combinational:** every bit reachable from the injected bit through combinational logic
  will appear X in the VCD, at the correct propagation time for that bit.
- **Sequential:** only the specific bits of FFs that actually captured X at a clock edge
  are included — correct clock phase and enable state are enforced by the simulation.

Since Layers 2 and 6 guarantee the injection is the only X source, any bit that is X in
the VCD after injection time is definitively caused by the injection.

`cone_members` is computed from the VCD post-simulation and stored in the manifest.

### Timing condition

For a `(signal, bit)` pair reported by the tracer at time T, the timing check is:

```
first_x_time(signal, bit) ≤ T ≤ first_x_time(signal, bit) + clock_period_ticks
```

where `first_x_time(signal, bit)` = the earliest VCD timestamp at which that specific bit
of the signal transitions to X at or after `injection_time`.

```python
def first_x_time(vcd, signal, bit, after):
    """Return earliest time bit `bit` of `signal` is X at or after `after`, or None."""
    for t, value in vcd.get_transitions(signal):
        if t < after:
            continue
        if get_bit(value, bit) == 'x':
            return t
    return None
```

### Grading rule

Tracer output is a set of `(signal[bit], time)` pairs. A tracer output passes a testcase
iff **all three** of the following hold:

1. **Root cause reached:** the injection target `signal[bit]` is in `tracer_output` — the
   tracer traced all the way back to the injected bit, including through carry chains,
   reconvergent paths, and sequential boundaries.
2. **Precision:** all reported `signal[bit]` entries are in `cone_members` — no fabricated
   paths.
3. **Focus:** `|tracer_output| ≤ 5` — the tracer returns a focused answer.

The timing condition applies to the injection target entry in `tracer_output`.

### Corpus-level vs. tracer-level separation

"Golden" is a property of the testcase, not the tracer. A testcase is golden when the
validation pipeline (Layers 1–6 below) passes and `cone_members` is computed and stored.
Grading a tracer against the corpus is a separate step: the tracer is run against all
golden VCDs and its outputs are checked against the stored `cone_members` sets. The corpus
can be built and validated without ever running the tracer under test.

---

## Open-Source Netlist Sources

### Tier 1: Automated pipeline targets (gate-level Verilog, combinational)

**ISCAS'85** — highest priority, automated pipeline primary source
- Pure combinational circuits, 17–2,600 gates
- Ideal for gate-model validation and combinational cone traversal
- Well-characterized topology; cone depths and fanout distributions are known
- Sources: `github.com/jpsety/verilog_benchmark_circuits`,
  `github.com/santoshsmalagi/Benchmarks`

**ITC'99 (combinational variants only)** — medium scale
- 29–70K gates, combinational variants only for automated pipeline
- Synthesized gate-level netlists included — no extra synthesis step
- Source: `github.com/cad-polito-it/I99T`, CC licensed

**HDL Benchmarks (TrustworthyComputing)** — RTL + Yosys-synthesized netlists paired
- Fast to onboard; netlists already generated; combinational subsets usable directly
- Source: `github.com/TrustworthyComputing/hdl-benchmarks`

### Tier 2: Hand-authored testbench targets (synthesize from RTL, sequential)

These require hand-authored testbenches. They contribute to `sequential/` and `stress/`
categories but are not automated pipeline targets.

**ISCAS'89** — sequential benchmarks with DFFs
- Gate-level injection restricted to primary inputs; meaningful sequential testcases
  require RTL-level `$deposit`, which is only available before synthesis
- Hand-authored testbenches use `$deposit` on the RTL source before synthesis to
  synthesize targeted sequential cases

**PicoRV32** (~8–15K gates) — best RISC-V option for realistic sequential X cases
- Synthesize: `yosys -p "synth -top picorv32; write_verilog netlist.v" picorv32.v`
- License: ISC — `github.com/YosysHQ/picorv32`

**Ibex** (~12–20K gates) — formally verified, well-characterized sequential logic
- License: Apache 2.0 — `github.com/lowRISC/ibex`

**CVA6** (~50–100K gates) — largest open RISC-V core, good stress-test depth
- License: Solderpad — `github.com/openhwgroup/cva6`

**EPFL Benchmarks** — arithmetic circuits up to 1M+ gates
- Multiplier, sqrt, adder — ideal for `stress/` deep-cone cases
- Source: `github.com/lsils/benchmarks`

### Tier 3: Real tapeout netlists (hand-authored, structural)

**Caravel / SkyWater PDK designs**
- Uses `sky130_fd_sc_hd__*` standard cells — validates cell library mapping
- Hand-authored testbenches required; used for `structural/` black-box and cell-library
  cases
- Source: `github.com/efabless/caravel`, Apache 2.0

---

## Synthetic Test Generation

Synthetic netlists are programmatically generated Verilog files designed to guarantee
exact coverage of specific X-propagation scenarios. They complement open-source netlists:
synthetics cover known scenarios precisely; open-source netlists cover realistic complexity.

### Tier S1 — Gate Primitive Cross-Product

A Python generator emits one testcase per entry in the cross-product of:
- Gate type × input arity × X-input pattern × non-X input values

```python
GATE_TYPES = ["and", "or", "nand", "nor", "xor", "xnor", "not", "buf",
              "bufif0", "bufif1"]

# For each gate type, enumerate all combinations of X/0/1 on inputs.
# Record expected output (X or a known value) for each combination.
for gate in GATE_TYPES:
    for arity in gate_arities(gate):           # e.g., AND: 2,3,4-input
        for x_mask in all_bitmasks(arity):     # which inputs are X
            for other in non_x_combinations(arity, x_mask):  # 0/1 on non-X inputs
                emit_gate_testcase(gate, arity, x_mask, other)
```

Each emitted testcase is a minimal Verilog module with one gate instance, one primary
input per gate input, and one primary output. The injection is `force` on the chosen
X input(s); the query is the gate output.

**Key cases this guarantees:**

| Gate | Scenario | Expected output |
|------|----------|----------------|
| AND | one input X, all others 1 | X |
| AND | one input X, one other 0 | 0 (X masked) |
| OR  | one input X, all others 0 | X |
| OR  | one input X, one other 1 | 1 (X masked) |
| XOR | one input X, other 0 | X |
| XOR | one input X, other 1 | X |
| XOR | both inputs X | X |
| NOT | input X | X |
| MUX | select X, both data equal | data value (X masked) |
| MUX | select X, data differ | X |
| MUX | select known, data input X | X or masked |

The generator also emits **chain** variants: the output of one gate feeds the input of the
next, testing that the tracer correctly traverses multi-gate combinational paths.

### Tier S2 — Structural Pattern Templates

Pre-written parameterised Verilog templates cover structural patterns that require more
than a single gate:

**`carry_chain.v` — N-bit ripple carry adder**
```
Parameters: WIDTH (default 8)
Injection:  force carry_in[0] = 1'bx  (or force a[0][0] = 1'bx)
Query:      sum[WIDTH-1][0]
Purpose:    Bit-level X propagation through carry chain; tests that tracer
            identifies carry_in[0] not sum[N-1] as root cause.
Widths:     4, 8, 16, 32
```

**`ff_chain.v` — N-deep D flip-flop chain**
```
Parameters: DEPTH (default 4)
Injection:  $deposit(ff[0].q, 1'bx)
Query:      ff[DEPTH-1].q[0]
Purpose:    Sequential depth; X propagates one FF per clock cycle.
            Tests that tracer crosses DEPTH sequential boundaries.
Depths:     1, 2, 4, 8
```

**`reconverge.v` — Diamond reconvergent fanout**
```
Parameters: DEPTH (default 3)
Injection:  force src[0] = 1'bx
Query:      merge_gate output[0]
Purpose:    Two paths from src to merge_gate; tracer must follow both and
            converge on the single injection point, not report intermediates.
Depths:     2, 4, 8
```

**`mux_tree.v` — Balanced binary mux tree**
```
Parameters: LEVELS (default 3), X_ON (select|data)
Injection:  force sel[level][0] = 1'bx   (X on select)
         or force data[leaf][0] = 1'bx   (X on data input)
Query:      root output[0]
Purpose:    X-on-select propagates regardless of data values;
            X-on-data may be masked by select. Tests both cases.
Levels:     2, 3, 4
```

**`reset_chain.v` — FF with synchronous/asynchronous reset**
```
Parameters: RESET_TYPE (sync|async), DEPTH (default 2)
Injection:  force rst_n[0] = 1'bx
Query:      ff[DEPTH-1].q[0]
Purpose:    X on reset propagates to all FF outputs; tests reset-path tracing.
```

**`bus_encoder.v` — Priority encoder with X on low-order input**
```
Parameters: WIDTH (default 8)
Injection:  force in[0] = 1'bx
Query:      out[WIDTH-1][0]
Purpose:    X propagates through priority logic; higher-order outputs go X
            because lower-order input is X (analogous to counter carry chain).
Widths:     4, 8
```

### Tier S3 — Multi-Bit Tests

Tiers S1 and S2 exercise single-bit injection and single-bit queries. Tier S3 exercises
the cases that only arise with buses: partial injection (some bits X, others known),
independent bit propagation through wide logic, and cross-bit effects (carry, shift,
reduction). These are the cases where a bus-level tracer silently gives wrong answers
while a bit-level tracer is required to give correct ones.

**`partial_bus_gate.v` — N-bit gate array with partial X injection**
```
Parameters: GATE_TYPE, WIDTH (4,8,16), X_BITS (which bits of input_a are X)
Injection:  force input_a[K] = 1'bx for each K in X_BITS; all other bits known
Query:      output[K][0] for each injected bit; output[K'][0] for a non-injected bit
Purpose:    Tracer must find input_a[K] for the X query, and must NOT report
            input_a[K] for the non-X query. Tests per-bit isolation.
Example:    8-bit AND, inject X on bits [2:0] only.
            output[0] is X → root cause is input_a[0].
            output[7] is 0 (masked or no X) → tracer should not reach input_a[0].
```

**`bit_slice.v` — Bit-select and part-select through logic**
```
Parameters: WIDTH (8,16), INJECT_BIT, QUERY_BIT, SLICE_OP (select|concat|replicate)
Injection:  force bus[INJECT_BIT] = 1'bx
Query:      output[QUERY_BIT][0]
Purpose:    Test that tracer follows bit-select operations correctly.
            e.g., out = {a[6], a[4], a[2], a[0]} — inject a[2], query out[1].
            Tracer must find a[2], not a[6] or a[0].
```

**`multibit_mux.v` — N-bit MUX with partial X on data input**
```
Parameters: WIDTH (4,8), INJECT_BITS (subset of [WIDTH-1:0]), SEL_VALUE (0|1)
Injection:  force data_a[K] = 1'bx for K in INJECT_BITS; sel driven to SEL_VALUE
Query:      out[K][0] for injected bit; out[K'][0] for non-injected bit
Purpose:    With sel known, only injected bits of the selected data input
            propagate to output. Tracer must identify the specific injected bit,
            not the entire data_a bus.
```

**`shift_reg.v` — N-bit shift register with bit-level X injection**
```
Parameters: WIDTH (8), INJECT_BIT, SHIFT_AMOUNT (1,2,4)
Injection:  force shift_reg[INJECT_BIT] = 1'bx at cycle 0
Query:      shift_reg[(INJECT_BIT + SHIFT_AMOUNT) % WIDTH][0] after SHIFT_AMOUNT cycles
Purpose:    X on bit K shifts to bit K+N after N clock cycles. Tracer must
            trace back through SHIFT_AMOUNT sequential boundaries and identify
            the original bit as root cause.
Widths × shifts: 8-bit × {1,2,4} = 3 cases
```

**`reduction.v` — Bitwise reduction with partial X**
```
Parameters: OP (and|or|xor), WIDTH (8), INJECT_BITS, OTHER_BIT_VALUE (0|1)
Injection:  force bus[K] = 1'bx for K in INJECT_BITS
Query:      reduced_out[0]
Purpose:    AND-reduction with one X bit and all others 1 → output X.
            AND-reduction with one X bit and one 0 → output 0 (X masked).
            OR-reduction with one X bit and one 1 → output 1 (X masked).
            Tracer must identify the injected bit, not the entire bus.
            Masking variants must not reach the injected bit (no X at output).
```

**`bit_interleave.v` — Bit reordering and concatenation across sources**
```
Parameters: WIDTH (8), INJECT_SRC (a|b), INJECT_BIT
Injection:  force src_a[INJECT_BIT] = 1'bx  (or src_b)
Query:      interleaved output bit corresponding to injected bit
            e.g., out = {a[3],b[3],a[2],b[2],a[1],b[1],a[0],b[0]}
            inject a[2] → query out[5]
Purpose:    Tracer must follow bit reordering; must not confuse a[2] with b[2]
            or a[3] even though all appear in the same output bus.
```

### Synthetic Test Generator Implementation

The generator is a standalone Python script `tests/gen_synthetic.py`:

```python
def generate_all(output_dir: Path):
    # Tier S1: gate cross-product (single-bit)
    for spec in gate_cross_product():
        emit_gate_case(spec, output_dir / "synthetic" / "gates")

    # Tier S2: structural templates (single-bit injection, structural complexity)
    for template, params in STRUCTURAL_TEMPLATES:
        for p in params:
            emit_structural_case(template, p, output_dir / "synthetic" / "structural")

    # Tier S3: multi-bit bus tests
    for template, params in MULTIBIT_TEMPLATES:
        for p in params:
            emit_multibit_case(template, p, output_dir / "synthetic" / "multibit")
```

Generated cases go through the same validation pipeline (Layers 1–6) as all other
testcases. `"generation": "synthetic"` is a third registry category alongside
`"auto-pipeline"` and `"manual"`.

### Synthetic Corpus Coverage Targets

| Category | Generator | Count |
|----------|-----------|-------|
| Gate cross-product (S1) | `gen_synthetic.py` | ~200 |
| Carry chain (S2) | `carry_chain.v` × 4 widths | 4 |
| FF chain (S2) | `ff_chain.v` × 4 depths | 4 |
| Reconvergent fanout (S2) | `reconverge.v` × 3 depths | 3 |
| Mux tree (S2) | `mux_tree.v` × 3 levels × 2 X targets | 6 |
| Reset chain (S2) | `reset_chain.v` × 2 types × 2 depths | 4 |
| Bus encoder (S2) | `bus_encoder.v` × 2 widths | 2 |
| Partial bus gate (S3) | `partial_bus_gate.v` × 3 gate types × 3 widths × inject patterns | ~30 |
| Bit slice (S3) | `bit_slice.v` × 3 ops × 2 widths | 6 |
| Multi-bit MUX (S3) | `multibit_mux.v` × 2 widths × inject patterns | ~10 |
| Shift register (S3) | `shift_reg.v` × 3 shift amounts | 3 |
| Reduction (S3) | `reduction.v` × 3 ops × masking/non-masking | ~12 |
| Bit interleave (S3) | `bit_interleave.v` × 2 sources × 4 bits | 8 |
| **Total synthetic** | | **~292** |

---

## Testcase Corpus Structure

```
tests/
├── cases/
│   ├── synthetic/          # Programmatically generated (Agent E)
│   │   ├── gates/          # Tier S1: gate cross-product (single-bit)
│   │   ├── structural/     # Tier S2: carry chains, FF chains, reconverge, mux trees
│   │   └── multibit/       # Tier S3: partial bus, bit-slice, shift, reduction, interleave
│   ├── combinational/      # Automated: ISCAS'85, ITC'99 combinational (Agent A)
│   │   ├── and_x_prop/
│   │   ├── or_masking/
│   │   ├── mux_select_x/
│   │   └── reconvergent/
│   ├── sequential/         # Hand-authored: ISCAS'89 RTL, PicoRV32, Ibex (Agent B)
│   │   ├── flop_uninit/
│   │   ├── latch_enable_x/
│   │   └── reset_x/
│   ├── structural/         # Hand-authored: black-box, multi-driver, boundary (Agent C)
│   │   ├── black_box/
│   │   └── multi_driver/
│   └── stress/             # Hand-authored: large netlists, deep cones (Agent D)
│       ├── deep_cone/
│       └── wide_reconvergence/
├── registry.json           # Merged index of all cases (append-only)
└── schema.json             # Manifest schema (read-only)
```

The registry distinguishes three generation categories: `"synthetic"`, `"auto-pipeline"`,
and `"manual"`. Coverage metrics are reported separately per category.

### Coverage Matrix

| Agent | Category | Generation | Source | Target count |
|-------|----------|------------|--------|-------------|
| Agent E | synthetic/gates | Synthetic (S1) | `gen_synthetic.py` gate cross-product | ~200 |
| Agent E | synthetic/structural | Synthetic (S2) | Verilog templates | ~23 |
| Agent E | synthetic/multibit | Synthetic (S3) | Multi-bit Verilog templates | ~69 |
| Agent A | combinational/* | Auto-pipeline | ISCAS'85 (c17, c432, c880, c2670) | 20 golden |
| Agent B | sequential/* | Hand-authored | ISCAS'89 RTL, PicoRV32, Ibex | 15 golden |
| Agent C | structural/* | Hand-authored | ITC'99 edge cases, SkyWater, custom | 10 golden |
| Agent D | stress/* | Hand-authored | EPFL multiplier, CVA6, PicoRV32 | 5 large |

---

## Manifest Schema

Every testcase has a `manifest.json`. All time fields are integers in simulator ticks.
Physical time is derivable from `sim_env.timescale` and is never stored directly.

```json
{
  "id": "comb_iscas85_c432_force_pi_001",
  "category": "combinational",
  "generation": "auto-pipeline",
  "netlist": {
    "file": "netlist.v",
    "sha256": "a3f9c...",
    "level": "gate"
  },
  "vcd": "sim.vcd",
  "testbench": "tb.v",
  "sim_env": {
    "simulator": "iverilog",
    "version": "12.0",
    "timescale": "1ns/1ps"
  },
  "timing": {
    "clock_period_ticks": 10,
    "clock_edge": "posedge"
  },
  "query": {
    "signal": "tb.dut.G49",
    "time": 150
  },
  "x_injection": {
    "method": "force",
    "target": "tb.dut.a",
    "value": "1'bx",
    "time": 80
  },
  "expected": {
    "oracle": "cone_membership_v2",
    "injection_target": "tb.dut.a[0]",
    "injection_time": 80,
    "query_signal": "tb.dut.G49[0]",
    "query_time": 150,
    "cone_members": ["tb.dut.a[0]", "tb.dut.G7[0]", "tb.dut.G11[0]", "tb.dut.G49[0]"]
  },
  "cone_depth": 3,
  "sequential_depth": 1,
  "status": "golden",
  "author": "agent-A"
}
```

Valid `injection_class` values: `primary_input`, `uninit_ff`.

The optional `structural_class` annotation (for hand-authored structural testcases only):
`black_box_boundary`, `multi_driver`, `module_port_crossing`. This field is for coverage
analysis only, not for grading.

### Injection Methods

The automated pipeline supports exactly two injection methods:

| Method | Applicable to | Verilog | Semantics |
|--------|--------------|---------|-----------|
| `force` on primary input | Gate-level netlists | `force tb.dut.a = 1'bx;` | Held for simulation duration; no competing driver; cannot be overwritten |
| `$deposit` on RTL reg | RTL-level designs only | `$deposit(tb.dut.acc_reg, 8'bx);` | One-time initialization of storage element; propagates as logic runs normally |

All other injection methods (internal nets, control nets, enables, gate outputs) require
hand-authored testbenches. They are not supported by the automated pipeline.

**Rationale for restriction:**
- `force` on a primary input has no competing driver. The injection persists without
  interaction effects from other drivers.
- `$deposit` on an RTL `reg` targets the storage element directly. Standard-cell flop
  outputs at gate level do not expose a writable state variable; `$deposit` is not used
  at gate level.
- Both methods are straightforwardly checkable by Layer 4 of the validation pipeline.

---

## Design Metadata (required for all designs with sequential elements)

Any design used in the automated pipeline that contains sequential elements must supply a
`design_meta.json` file. Designs without this file are rejected from automated generation.
ISCAS'85 circuits are purely combinational and exempt.

```json
{
  "top_module": "c432",
  "clock_port": "clk",
  "clock_period_ticks": 10,
  "reset": {
    "port": "rst_n",
    "polarity": "active_low",
    "type": "synchronous",
    "min_assertion_cycles": 8,
    "requires_clock_during_assertion": true
  },
  "scan_ports": ["scan_en", "test_mode"],
  "multi_clock": false
}
```

Multi-clock designs (`multi_clock: true`) are out of scope for the automated pipeline.
They require hand-authored testbenches. Single-clock designs must declare one `clock_port`;
the generated testbench drives exactly that port.

Reset polarity and type are not inferred at generation time. If the metadata is missing or
incomplete, the design is rejected. For Tier 1 benchmarks (ISCAS'85, ITC'99 combinational),
no reset metadata is needed as these are combinational circuits.

---

## Clean Simulation Environment (mandatory)

Before injecting X, the simulation must have zero X or Z values anywhere. This is enforced
by Layer 2 of the validation pipeline.

**Rule 1: All primary inputs driven with known values**
```verilog
initial begin
    a = 1'b0; b = 1'b1; sel = 1'b0;  // explicit, no implicit Z
end
```

**Rule 2: All sequential elements initialized via reset (when reset port exists)**
```verilog
initial begin
    rst_n = 0;
    repeat(8) @(posedge clk);   // hold reset long enough to flush all FFs
    rst_n = 1;
    repeat(16) @(posedge clk);  // settle to clean state — zero X/Z in VCD here
    // NOW inject X
    $deposit(top.u_alu.acc_reg, 8'bx);
end
```
Reset assertion length and clock requirements come from `design_meta.json`.

**Rule 3: Scan/test inputs held at safe values**

Signals matching `/scan_en|test_mode|mbist|bist|\bse\b/i` are driven to their safe
(functional) value (typically 0) and never treated as data inputs. A `design_meta.json`
`scan_ports` array lists these explicitly.

**Rule 4:** No tristates left floating — pull all `inout` ports to a known value.

**Rule 5:** Deterministic stimulus only — no `$random` without a fixed seed documented in
`build.json`.

---

## Testbench Generation for Downloaded Netlists

Downloaded netlists fall into two paths:

```
Does a sufficient testbench exist?
  ├── No  → Auto-generate (automated pipeline)
  └── Yes → Hand-authored mode (out of automated pipeline scope)
```

Existing testbenches are never modified and never wrapped by the automated pipeline.
Designs that require a preserved existing testbench (complex protocol environment, memory
models, etc.) are classified as requiring hand-authored work and are out of scope for
automated generation.

### Auto-Generate Path

Parse the top-level module ports using `pyslang`, classify them using `design_meta.json`,
emit a standard template.

**Port classification (from design_meta.json, not heuristics):**

Clock and reset ports are taken from `design_meta.json`. Scan/test ports are taken from
`scan_ports`. All remaining inputs are data inputs driven to 0.

**Generated testbench template:**
```verilog
`timescale 1ns/1ps
module tb;
  // --- port declarations (filled from netlist port list) ---
  reg clk, rst_n;
  reg [W-1:0] data_in;   // one per data input port, driven to 0

  // --- scan/test ports held at safe value ---
  reg scan_en = 0;

  // --- DUT instantiation ---
  // All paths in manifest are rooted at tb.dut
  top_module dut (.clk(clk), .rst_n(rst_n), .in(data_in), .scan_en(scan_en), ...);

  // --- VCD dump (full hierarchy from tb) ---
  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  // --- Clock ---
  initial clk = 0;
  always #(`CLOCK_HALF_PERIOD) clk = ~clk;

  // --- Stimulus: reset then drive known values ---
  initial begin
    rst_n = 0;
    data_in = 0;
    repeat(`RESET_CYCLES) @(posedge clk);
    rst_n = 1;
    repeat(`SETTLE_CYCLES) @(posedge clk);  // settle to clean state
    // --- INJECTION POINT (filled by harness via -D defines) ---
    `ifdef INJECT_FORCE
      force `INJECT_TARGET = `INJECT_VALUE;
    `elsif INJECT_DEPOSIT
      $deposit(`INJECT_TARGET, `INJECT_VALUE);
    `endif
    repeat(`PROPAGATION_CYCLES) @(posedge clk);  // let X propagate
    $finish;
  end

  // --- Hard timeout ---
  initial #`SIM_TIMEOUT $finish;
endmodule
```

The harness fills `INJECT_TARGET`, `INJECT_VALUE`, `CLOCK_HALF_PERIOD`, `RESET_CYCLES`,
`SETTLE_CYCLES`, `PROPAGATION_CYCLES`, and `SIM_TIMEOUT` via `-D` defines passed to
`iverilog`. These values, along with all compilation flags and library files, are recorded
in `build.json` for reproducibility.

Default values: `RESET_CYCLES = 8`, `SETTLE_CYCLES = 16`, `PROPAGATION_CYCLES = 64`.

Queries are always placed at `N * clock_period_ticks + half_period_ticks` — between rising
edges — where no active NBA updates should be in flight for synchronous designs.

**ISCAS'85 (no clock, no reset):** For purely combinational circuits, the testbench drives
all inputs to known values, applies the force injection, waits `#20` for settling, then
emits a query. No clock or reset logic is generated.

---

## Signal Hierarchy Scanner

Used to enumerate candidate injection targets for downloaded netlists.

```python
def scan_injection_candidates(netlist: NetlistGraph) -> list[InjectionCandidate]:
    candidates = []
    for signal in netlist.all_signals():
        if signal in design_meta.scan_ports:  continue
        if is_power_ground(signal):            continue  # VDD/VSS/VDDIO etc.
        if is_clock(signal, design_meta):      continue  # forcing clk causes chaos

        fanout = len(netlist.get_fanout(signal))
        if fanout == 0: continue  # X won't propagate anywhere useful

        candidates.append(InjectionCandidate(
            signal=signal,
            fanout=fanout,
            is_ff_output=netlist.get_driver(signal).type in SEQUENTIAL_TYPES,
            is_primary_input=netlist.is_primary_input(signal),
            # cone_depth computed from VCD post-simulation, not pre-computed here
        ))
    return candidates
```

**Selection strategy for ISCAS'85 (combinational, gate-level, primary-input injection):**

The 5 injection targets per netlist are chosen to cover structurally distinct traversal
scenarios — the hard cases for a backward-cone tracing algorithm:

1. **Deepest primary input** — the primary input whose forward cone reaches the farthest
   output in terms of gate depth; tests deep combinational traversal
2. **Input at a reconvergent point** — a primary input whose forward cone reaches a
   downstream gate via two or more disjoint paths; tests reconvergence handling.
   Detected by: find nodes in the netlist whose forward cones overlap; trace back to a
   primary input that causes the overlap.
3. **Input crossing a module-port boundary** — a primary input that feeds a sub-module
   port on the path to the output; tests cross-module signal-path resolution
4. **Shallowest direct-path input** — the primary input with the shortest unmasked path
   to any primary output (baseline combinational, minimum intermediate signals)
5. **Randomly sampled primary input** from those not selected by criteria 1–4 (diversity)

For RTL hand-authored testbenches, criterion 1 may use FF outputs (`$deposit` targets)
in addition to primary inputs.

**5 query signals per injection** are chosen to cover distinct structural positions:
1. Immediate combinational fanout of the injection point
2. Across the first module-port boundary from the injection point
3. At a reconvergent merge point
4. At maximum cone depth reachable within the simulation window
5. At a primary output boundary

All 5 must have distinct `cone_depth_class` — no two testcases from the same run share
both injection target and cone-depth tier.

---

## Testcase Generation Flow

```
1. Obtain netlist (ISCAS'85 download; or synthesize from RTL for hand-authored cases)
2. Verify design_meta.json is present and complete (skip for combinational-only designs)
3. Freeze netlist: compute SHA-256 checksum, store in manifest
4. Scan signal hierarchy → candidate injection targets (5 per netlist, selection above)
5. For each injection target, select 5 structurally diverse query signals
6. Generate testbench from template (auto-gen path) or use hand-authored testbench
7. Record build.json: simulator version, all -D defines, library files, compilation flags
8. Run simulation with injection → VCD
9. Validate: Layers 1–6 (see below)
10. Compute cone_members at bit level: scan VCD for all (signal, bit) pairs where that
    bit transitions to X after injection_time; store as "signal[bit]" strings
11. Compute cone_depth: count of distinct X-carrying (signal, bit) pairs on the shortest
    VCD-observed path from injection bit to query bit; verify cone_depth ≥ 3
12. Compute sequential_depth: number of clock-edge boundaries crossed on the path from
    injection bit to query bit (0 for purely combinational testcases)
13. Store manifest with cone_members, cone_depth, sequential_depth, SHA-256, sim_env,
    timing fields; injection_target and query_signal in "signal[bit]" form
13. Append to registry.json
```

---

## Validation Pipeline

Every testcase must pass all layers before entering the corpus:

```
[Layer 1] iverilog + slang lint
          — syntax, elaboration, undefined references
          — FAIL → rejected, agent gets error

[Layer 2] Zero X or Z in VCD before injection time
          — confirms clean simulation environment
          — checks initial signal values AND all transitions before injection
          — FAIL → testbench rejected (environment not clean)

[Layer 3] Queried signal is X at query time
          — confirms X actually reached the query point
          — FAIL → injection didn't propagate, discard testcase

[Layer 4] Injection target is X in VCD at injection time
          — confirms force/deposit took effect
          — for $deposit: verify X persisted for at least one clock cycle
          — FAIL → testbench bug

[Layer 5] Manifest schema lint
          — valid injection_class, non-negative times, signal paths exist in elaborated
            hierarchy, cone_members is non-empty, cone_depth ≥ 3, sequential_depth present
          — FAIL → rejected

[Layer 6] Counterfactual check: simulation without injection
          — run identical simulation with injection block removed
          — verify query signal is NOT X at query time
          — FAIL → secondary X source exists independent of injection; testcase discarded
```

**Layer 2 implementation:**

```python
def contains_unknown(value: str) -> bool:
    """True if VCD value contains any X or Z bit."""
    v = value.lower().lstrip('b')
    return any(c in ('x', 'z') for c in v)

def validate_clean_sim(vcd: VCDDatabase, injection_time: int):
    for sig in vcd.all_signals():
        # Check initial value (before any transition at t=0)
        initial = vcd.get_initial_value(sig)
        if initial is not None and contains_unknown(initial):
            raise CleanEnvError(
                f"DIRTY ENV: {sig} starts as {initial!r} before injection at t={injection_time}\n"
                f"  Fix: add $deposit({sig}, 0) to initialization block, or check reset logic."
            )
        # Check all transitions before injection time
        for (t, v) in vcd.get_transitions(sig):
            if t >= injection_time:
                break
            if contains_unknown(v):
                raise CleanEnvError(
                    f"DIRTY ENV: {sig} = {v!r} at t={t} before injection at t={injection_time}\n"
                    f"  Fix: ensure reset is held long enough, or check for uninitialized FFs."
                )
```

The VCD parser must expose `get_initial_value()`. If the parser does not support this, it
is not suitable for Layer 2.

Layer 2 failures are always a testbench problem — either an uninitialized FF or an
undriven input. The error output lists the offending signals with suggested fixes.

---

## Golden Promotion Criteria

A testcase is promoted to `status: "golden"` iff it passes **all** of the following:

1. **Layers 1–6** of the validation pipeline pass
2. **Cone computation succeeds:** `cone_members` is computed from the VCD at bit level and
   is non-empty; at minimum the injected bit and the queried bit are present.
3. **Minimum cone depth:** `cone_depth ≥ 3` — at least 2 intermediate signals exist
   between injection target and query signal on the observed X-propagation path. Testcases
   where injection directly drives the query with no intermediate logic are rejected (no
   traversal exercise).
3a. **Sequential depth recorded:** `sequential_depth` is computed and stored; testcases
    with `sequential_depth ≥ 1` must have a valid `design_meta.json` with clock metadata.
4. **Manifests is complete:** all required fields present and schema-valid (Layer 5)

"Golden" is a property of the testcase, established without running the tracer under test.
The grading oracle (cone membership check) is applied separately when evaluating a tracer
implementation against the corpus.

### Grading rule (applied during tracer evaluation, not during corpus construction)

Given a tracer's output `T_out` = set of `(signal, time)` pairs for a given testcase:

```python
def grade(tracer_output, manifest, vcd):
    """
    tracer_output: list of ("signal[bit]", time) pairs
    cone_members:  set of "signal[bit]" strings, computed from VCD at corpus build time
    """
    injection_target = manifest["expected"]["injection_target"]  # e.g. "tb.dut.a[0]"
    cone = set(manifest["expected"]["cone_members"])
    bits_reported = {sig_bit for sig_bit, t in tracer_output}

    # Root cause: tracer must reach the injected bit.
    # Carry chains, reconvergent fanout, and sequential boundaries must all be
    # traversed — stopping at any intermediate bit is a tracer failure.
    if injection_target not in bits_reported:
        return FAIL, f"Tracer did not reach injection point {injection_target!r}"

    # Precision: no bit outside the cone — no fabricated paths
    outside = bits_reported - cone
    if outside:
        return FAIL, f"Bits outside cone: {outside}"

    # Focus: bounded output size
    if len(tracer_output) > 5:
        return FAIL, f"Tracer returned {len(tracer_output)} results; maximum is 5"

    # Timing: injection target must be reported at a plausible time
    inj_time = manifest["x_injection"]["time"]
    period = manifest["timing"]["clock_period_ticks"]
    sig, bit = parse_sig_bit(injection_target)   # "tb.dut.a[0]" -> ("tb.dut.a", 0)
    for reported_sig_bit, t in tracer_output:
        if reported_sig_bit == injection_target:
            first_x = first_x_time(vcd, sig, bit, after=inj_time)
            if first_x is not None and abs(t - first_x) <= period:
                return PASS, f"Correctly reached {injection_target!r} at t={t}"

    return FAIL, f"Injection target {injection_target!r} reported at wrong time"
```

**Black-box cases:** For a signal at a black-box input boundary, `first_x_time` is the
time at which that input transitioned to X. Reporting any X-carrying black-box input on
the path from injection to query is a valid answer. The oracle accepts observability-limit
answers; testing inferences about black-box internals is not possible without knowing
those internals and is explicitly out of scope.
