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
completely clean before injection — all inputs driven, all registers initialized — and
verifying via the counterfactual check (Layer 6) that the query would not be X without
injection, the injection is the unique source of X on the traced path. The expected answer
is always the injection point; the corpus can be built and graded without any reference
simulator.

### Why synthetic tests

Open-source netlists provide realistic structural complexity but offer no guarantee that
any specific gate type, propagation scenario, or structural pattern is present. A corpus
built only from downloaded netlists may miss entire classes of tracer bugs — for example,
a bug in XOR X-propagation will never be caught if no ISCAS benchmark happens to exercise
a two-input XOR with exactly one X input under the chosen stimulus.

Synthetic netlists are programmatically generated to guarantee exact coverage of:
- Every synthesized Boolean gate primitive with every relevant combination of X and non-X inputs
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

- Any signal that is X in the injection VCD at or after injection time **and** is not X in
  the no-injection VCD at the same time is on the forward cone of the injection point
- Under the clean-environment invariant and single-injection constraint, the injection
  point is the origin of the X trajectory traced by the grading rule — including in
  reconvergent fanout cases where multiple paths from the injection point converge on the
  query signal
- The tracer is expected to trace all paths back to the injection point; stopping at an
  intermediate signal is a tracer bug, not an accepted answer
- No reference simulator is required for automated testcases

---

## Tracer Evaluation Oracle

This section defines the oracle used to grade tracer outputs against the corpus. This
definition is authoritative; no separate semantics document is required for automated
testcases.

### VCD as the oracle

Since the only source of X in any testcase (post-Layer 6 validation) is the explicitly
injected X, every bit that is X in the injection VCD at or after injection time **and**
not X in the no-injection VCD at the same time is definitively caused by the injection.
Both VCDs are the oracle — no pre-computed cone membership is stored in the manifest.

Bit-level tracking is required. Bus-level membership is insufficient: consider a counter
where `count[0]` goes X first due to an X carry-in, then `count[1]` goes X one cycle
later through carry propagation, and `count[7]` only goes X several cycles after that.
A bus-level tracer collapses all bits of `count` and loses causal ordering — the tracer
must identify `count[0]` as the root cause, not `count[7]`.

The canonical string form for all tracer outputs is `signal[bit]` — e.g.,
`tb.dut.count[0]`, `tb.dut.result[3]`. Scalars (width = 1) are represented as `sig[0]`.

### Grading rule

Tracer output is a set of `(signal[bit], time)` pairs. The grading function takes the
injection VCD, the no-injection VCD (produced by extended Layer 6), and the netlist graph.
A tracer output passes a testcase iff **all four** of the following hold:

1. **Root cause reached:** the injection target `signal[bit]` is in `tracer_output` — the
   tracer traced all the way back to the injected bit, including through carry chains,
   reconvergent paths, and sequential boundaries.

2. **Structural path:** every `signal[bit]` in `tracer_output` has a structural netlist
   path to the query signal — i.e., the reported bit is an ancestor of the query signal
   in the gate-level netlist graph. This is a graph reachability check (no gate semantics);
   it catches entirely unrelated signals while over-approximating to avoid requiring the
   oracle to evaluate masking.

3. **Time and independence:** for every `(signal[bit], t)` in `tracer_output`:
   - `t ≥ first_x_time(sig, bit, after=inj_time)` in the injection VCD — the reported
     time is not before the signal was actually X (no fabricated early reports)
   - the signal is not X at time `t` in the no-injection VCD — the reported X at that
     time is injection-caused, not an independent source

4. **Focus:** `|tracer_output| ≤ max_output` where `max_output` is taken from
   `manifest["expected"]["max_output"]`. For synthetic cases the generator sets this
   to the known expected answer size; for auto-pipeline cases the default is 10.

```python
def grade(tracer_output, manifest, inject_vcd, no_inject_vcd, netlist):
    injection_target = manifest["expected"]["injection_target"]
    inj_time = manifest["x_injection"]["time"]
    query_signal = manifest["expected"]["query_signal"]
    max_output = manifest["expected"].get("max_output", 10)
    bits_reported = {sig_bit for sig_bit, t in tracer_output}

    # Root cause: tracer must reach the injected bit
    if injection_target not in bits_reported:
        return FAIL, f"Did not reach injection point {injection_target!r}"

    for sig_bit, t in tracer_output:
        sig, bit = parse_sig_bit(sig_bit)

        # Structural path: reported bit must be an ancestor of query in netlist
        if not netlist.has_structural_path(sig_bit, query_signal):
            return FAIL, (
                f"{sig_bit} has no structural path to query {query_signal!r} "
                "— unrelated signal"
            )

        # Time lower bound: not before first observed X in injection VCD
        first_x = inject_vcd.get_first_x_time(sig, bit, after=inj_time)
        if first_x is None:
            return FAIL, f"{sig_bit} never X in injection VCD after injection — fabricated"
        if t < first_x:
            return FAIL, (
                f"{sig_bit}: reported t={t} before first observed X at t={first_x}"
            )

        # Independence: not X at this time in no-injection run
        if no_inject_vcd.get_value(sig, bit, at=t) == 'x':
            return FAIL, (
                f"{sig_bit} at t={t} is X even without injection — independent source"
            )

    # Focus: bounded output size
    if len(tracer_output) > max_output:
        return FAIL, f"Too many results: {len(tracer_output)} > {max_output}"

    return PASS, f"Reached {injection_target}"
```

### Corpus-level vs. tracer-level separation

"Golden" is a property of the testcase, not the tracer. A testcase is golden when the
validation pipeline (Layers 1–6 below) passes. Grading a tracer against the corpus is a
separate step: the tracer is run against all golden VCDs and its outputs are checked
using the grading rule above. The corpus can be built and validated without ever running
the tracer under test.

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

Target counts for Tier 1 assume approximately 70% pipeline yield on downloaded netlists;
actual counts depend on netlist characteristics (initialization behavior, port naming,
absence of tristate buses).

### Tier 2: Hand-authored testbench targets (synthesize from RTL, sequential)

These require hand-authored testbenches. They contribute to `sequential/` and `stress/`
categories but are not automated pipeline targets.

Sequential cases use `$deposit` on RTL `reg` state elements before synthesis. The manifest
`injection_target` must name the gate-level flop output confirmed by the synthesis name
map (Yosys preserves RTL source names as cell attributes in its JSON output). If synthesis
does not map the RTL reg to a uniquely identifiable gate-level flop — due to retiming,
duplication, resource sharing, or register splitting — the case is abandoned. This is a
genuine constraint: realistic synthesis optimizations can make specific RTL regs
unsuitable as injection targets. The advertised target counts assume sufficiently
conservative synthesis settings (no retiming, `synth -flatten`) and conventional register
structures.

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

Coverage scope: **every synthesized Boolean gate primitive** — `and`, `or`, `nand`,
`nor`, `xor`, `xnor`, `not`, `buf`, `bufif0`, `bufif1`. Switch-level primitives
(`tran`, `tranif0/1`, `cmos`, `nmos`, `pmos`) and user-defined primitives (UDPs) are out
of scope for S1 synthetic coverage; designs using them require hand-authored testbenches.

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

For S1 synthetic cases, the query signal is the gate output — exactly one gate from the
injection point. The `MIN_QUERY_DEPTH` filter applied to auto-pipeline query selection
(see § Signal Hierarchy Scanner) does not apply to S1 synthetic cases; single-gate
distance is the intended structural property under test.

The manifest for each S1 case records `expected.max_output = 2` (injection target + gate
output) to reflect the known expected answer size.

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
| bufif0 | input X, enable asserted | X |
| bufif0 | input known, enable X | X |

The generator also emits **chain** variants: the output of one gate feeds the input of the
next, testing that the tracer correctly traverses multi-gate combinational paths.

### Tier S2 — Structural Pattern Templates

Pre-written parameterised Verilog templates cover structural patterns that require more
than a single gate. This tier includes all mux semantics (X on select vs. X on data),
which are not expressible as a Verilog gate primitive and belong here rather than in S1.

**`carry_chain.v` — N-bit ripple carry adder**
```
Parameters: WIDTH (default 8)
Injection:  force carry_in[0] = 1'bx  (or force a[0][0] = 1'bx)
Query:      sum[WIDTH-1][0]
Purpose:    Bit-level X propagation through carry chain; tests that tracer
            identifies carry_in[0] not sum[N-1] as root cause.
Widths:     4, 8, 16, 32
max_output: WIDTH + 1
```

**`ff_chain.v` — N-deep D flip-flop chain**
```
Parameters: DEPTH (default 4)
Injection:  $deposit(ff[0].q, 1'bx)
Query:      ff[DEPTH-1].q[0]
Purpose:    Sequential depth; X propagates one FF per clock cycle.
            Tests that tracer crosses DEPTH sequential boundaries.
Depths:     1, 2, 4, 8
max_output: DEPTH + 1
```

**`reconverge.v` — Diamond reconvergent fanout**
```
Parameters: DEPTH (default 3)
Injection:  force src[0] = 1'bx
Query:      merge_gate output[0]
Purpose:    Two paths from src to merge_gate; tracer must follow both and
            converge on the single injection point, not report intermediates.
Depths:     2, 4, 8
max_output: 2*DEPTH + 1
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
max_output: LEVELS + 1
```

**`reset_chain.v` — FF with synchronous/asynchronous reset**
```
Parameters: RESET_TYPE (sync|async), DEPTH (default 2)
Injection:  force rst_n[0] = 1'bx
Query:      ff[DEPTH-1].q[0]
Purpose:    X on reset propagates to all FF outputs; tests reset-path tracing.
max_output: DEPTH + 1
```

**`bus_encoder.v` — Priority encoder with X on low-order input**
```
Parameters: WIDTH (default 8)
Injection:  force in[0] = 1'bx
Query:      out[WIDTH-1][0]
Purpose:    X propagates through priority logic; higher-order outputs go X
            because lower-order input is X (analogous to counter carry chain).
Widths:     4, 8
max_output: WIDTH + 1
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
max_output: 2 (injection target + one gate output)
```

**`bit_slice.v` — Bit-select and part-select through logic**
```
Parameters: WIDTH (8,16), INJECT_BIT, QUERY_BIT, SLICE_OP (select|concat|replicate)
Injection:  force bus[INJECT_BIT] = 1'bx
Query:      output[QUERY_BIT][0]
Purpose:    Test that tracer follows bit-select operations correctly.
            e.g., out = {a[6], a[4], a[2], a[0]} — inject a[2], query out[1].
            Tracer must find a[2], not a[6] or a[0].
max_output: 2
```

**`multibit_mux.v` — N-bit MUX with partial X on data input**
```
Parameters: WIDTH (4,8), INJECT_BITS (subset of [WIDTH-1:0]), SEL_VALUE (0|1)
Injection:  force data_a[K] = 1'bx for K in INJECT_BITS; sel driven to SEL_VALUE
Query:      out[K][0] for injected bit; out[K'][0] for non-injected bit
Purpose:    With sel known, only injected bits of the selected data input
            propagate to output. Tracer must identify the specific injected bit,
            not the entire data_a bus.
max_output: 2
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
max_output: SHIFT_AMOUNT + 1
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
max_output: 2
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
max_output: 2
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

For each emitted case the generator writes `expected.max_output` into the manifest using
the known expected answer size (injection target + path length, as documented in each
template above). Generated cases go through the same validation pipeline (Layers 1–6) as
all other testcases. `"generation": "synthetic"` is a third registry category alongside
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
| Agent A | combinational/* | Auto-pipeline | ISCAS'85 (c17, c432, c880, c2670) | ~20 golden (aspirational; ~70% yield) |
| Agent B | sequential/* | Hand-authored | ISCAS'89 RTL, PicoRV32, Ibex | ~15 golden (aspirational; synthesis constraints apply) |
| Agent C | structural/* | Hand-authored | ITC'99 edge cases, SkyWater, custom | ~10 golden |
| Agent D | stress/* | Hand-authored | EPFL multiplier, CVA6, PicoRV32 | ~5 large |

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
  "no_inject_vcd": "sim_no_inject.vcd",
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
    "signal": "tb.dut.G49[0]",
    "time": 150
  },
  "x_injection": {
    "method": "force",
    "target": "tb.dut.a[0]",
    "value": "1'bx",
    "time": 80,
    "injection_class": "primary_input"
  },
  "expected": {
    "injection_target": "tb.dut.a[0]",
    "injection_time": 80,
    "query_signal": "tb.dut.G49[0]",
    "query_time": 150,
    "max_output": 10
  },
  "status": "golden",
  "author": "agent-A"
}
```

All signal fields use `signal[bit]` form throughout. Scalars are written as `sig[0]`.

Valid `injection_class` values: `primary_input`, `uninit_ff`.

The optional `structural_class` annotation (for hand-authored structural testcases only):
`black_box_boundary`, `multi_driver`, `module_port_crossing`. This field is for coverage
analysis only, not for grading.

For sequential hand-authored cases where injection targets an RTL `reg`, the optional
field `rtl_source` records the RTL signal name (e.g., `"acc_reg[3]"`); `injection_target`
always names the gate-level flop output confirmed by the synthesis name map.

### Injection Methods

The automated pipeline supports exactly two injection methods:

| Method | Applicable to | Verilog | Semantics |
|--------|--------------|---------|-----------|
| `force` on primary input | Gate-level netlists | `force tb.dut.a[0] = 1'bx;` | Held for simulation duration; no competing driver; cannot be overwritten |
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

## Probe Simulation and Injection Time

The automated pipeline uses a **probe simulation** to determine the injection time
`T_inject` without requiring manual reset timing metadata.

### Probe simulation flow

```
1. Compile the netlist with the generated testbench (no injection block)
2. Run simulation up to a probe window limit (default: 4096 clock ticks)
3. Scan the probe VCD for X/Z transitions only:
```

```python
def find_injection_time(vcd: VCDDatabase, probe_limit: int) -> int | None:
    """
    Return T_inject = one tick after the last X/Z transition in the VCD,
    or None if the design never reaches a fully clean state within the window.

    Returns None when:
      - the last observed X/Z transition is at or beyond probe_limit
        (cannot confirm cleanliness up to the window edge)
      - the design had X/Z on some signal for the entire probe window

    Post-window clock transitions (which exist in every clocked design) do NOT
    trigger None — only X/Z valued transitions are examined.
    """
    last_x_time = -1
    for sig in vcd.all_signals():
        for t, value in vcd.get_transitions(sig):
            if not contains_unknown(value):
                continue   # skip known-value transitions entirely
            if t >= probe_limit:
                return None  # X/Z persisted to or beyond the window edge
            last_x_time = max(last_x_time, t)

    if last_x_time < 0:
        return 0   # design was X-free throughout
    candidate = last_x_time + 1
    if candidate >= probe_limit:
        return None  # last X was right at the window edge; can't confirm clean
    return candidate
```

If `None` is returned (design never fully cleans up within the probe window), the design
is rejected from the automated pipeline.

```
4. T_inject = find_injection_time(probe_vcd, probe_limit)
   — If None (never clean): reject design
5. Recompile with injection at T_inject
6. Run injection simulation → sim.vcd
7. Recompile without injection block (identical testbench, no force/deposit)
8. Run no-injection simulation → sim_no_inject.vcd (used by Layer 6 and grading)
```

The probe simulation uses a conservative testbench with 32 clock cycles of reset
assertion and 32 cycles of post-reset settle time. If the design needs more than this to
initialize, it must use hand-authored testbenches.

For combinational designs (ISCAS'85), there is no clock or reset. The probe simulation
applies known values to all inputs and waits `#20` ticks; `T_inject` is `#20`.

Multi-clock designs are out of scope for the automated pipeline and require hand-authored
testbenches.

---

## Clean Simulation Environment (mandatory)

Before injecting X, the simulation must have zero X or Z values anywhere. This is enforced
by Layer 2 of the validation pipeline. The probe simulation (see above) verifies this
automatically — `T_inject` is set to the first time the design is fully clean.

**Rule 1: All primary inputs driven with known values**
```verilog
initial begin
    a = 1'b0; b = 1'b1; sel = 1'b0;  // explicit, no implicit Z
end
```

**Rule 2: All sequential elements initialized via reset**
```verilog
initial begin
    rst_n = 0;
    repeat(32) @(posedge clk);   // conservative reset; probe sim confirms clean
    rst_n = 1;
    repeat(32) @(posedge clk);   // settle; T_inject determined from probe VCD
    // Injection fires at T_inject as determined by probe simulation
end
```

**Rule 3: Scan/test inputs held at safe values**

Signals matching `/scan_en|test_mode|mbist|bist|\bse\b/i` are driven to their safe
(functional) value (typically 0) and never treated as injection targets.

**Rule 4:** Designs with `inout` ports are rejected from the automated pipeline unless the
port is a testbench-internal signal with known direction (e.g., a scan chain). Bidirectional
bus handling requires hand-authored testbenches where the external model drives the bus
correctly.

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

Parse the top-level module ports using `pyslang`, classify them using
name heuristics, emit a standard template.

**Port classification (heuristics):**

Clock ports: name matches `/clk|clock|ck/i`, 1-bit input. Reset ports: name matches
`/rst|reset|rstn|rst_n/i`, 1-bit input. Scan/test ports: name matches
`/scan_en|test_mode|mbist|bist|\\bse\\b/i`. All remaining inputs are data inputs driven
to 0.

These heuristics are appropriate for the ISCAS'85, ITC'99, and HDL Benchmarks sources,
which use conventional port names. Designs with unconventional names will fail Layer 2
(pre-injection X/Z) and be rejected from the automated pipeline; this is the correct
outcome, not a bug in the heuristic. The ~70% yield assumption for target counts accounts
for this.

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

**Query time selection** depends on design type:
- **Synchronous designs:** query at `N * clock_period_ticks + half_period_ticks` —
  between rising edges, where no active NBA updates should be in flight.
- **Asynchronous reset designs:** query time is taken directly from the injection VCD
  as the first time the query signal transitions to X after `T_inject`. This is
  computed during step 8d of the generation flow.
- **Combinational designs (ISCAS'85):** query at `T_inject + 20` — after combinational
  settling.

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
        if is_clock_by_name(signal):   continue  # heuristic: /clk|clock|ck/i, 1-bit
        if is_power_ground(signal):    continue  # VDD/VSS/VDDIO etc.
        if is_scan_port_by_name(signal): continue  # /scan_en|test_mode|mbist|bist|\bse\b/i

        fanout = len(netlist.get_fanout(signal))
        if fanout == 0: continue  # X won't propagate anywhere useful

        candidates.append(InjectionCandidate(
            signal=signal,
            is_primary_input=netlist.is_primary_input(signal),
        ))
    return candidates
```

**Clock and scan detection** uses name heuristics only. A signal is excluded as a clock
candidate if its name matches `/clk|clock|ck/i` and it is 1-bit; scan/test ports are
excluded if the name matches `/scan_en|test_mode|mbist|bist|\bse\b/i`.

**Injection target selection:** pick up to 5 candidates using a seed derived from the
netlist SHA-256: `seed = int(sha256[:8], 16)`. The seed is recorded in `build.json`.
This makes corpus composition reproducible from the same netlist file. Preferring primary
inputs for combinational designs.

**Query signal selection:** after the injection simulation, scan the VCD for all
`(signal, bit)` pairs that are X after `T_inject` **and** not X in the no-injection VCD
at the same time. From these candidates, apply the following filters for
**auto-pipeline cases only** (not synthetic cases):

```python
def pick_query_signals(
    inject_vcd, no_inject_vcd, injection_target, inj_time, netlist
) -> list[str]:
    candidates = []
    for sig_bit in inject_vcd.all_x_bits_after(inj_time):
        # Skip the injection target itself (trivially the injection)
        if sig_bit == injection_target:
            continue
        # Skip bits that are X in the no-injection run at the same time
        sig, bit = parse_sig_bit(sig_bit)
        first_x = inject_vcd.get_first_x_time(sig, bit, after=inj_time)
        if no_inject_vcd.get_value(sig, bit, at=first_x) == 'x':
            continue
        # For auto-pipeline: skip trivially shallow targets
        gate_distance = netlist.min_gate_distance(injection_target, sig_bit)
        if gate_distance < MIN_QUERY_DEPTH:   # MIN_QUERY_DEPTH = 2 for auto-pipeline
            continue
        candidates.append(sig_bit)

    if not candidates:
        return []  # discard this injection run
    # Pick at most 3 from candidates, distributed across gate distances
    return stratified_pick(
        candidates,
        key=lambda s: netlist.min_gate_distance(injection_target, s),
        n=3
    )
```

`MIN_QUERY_DEPTH = 2` applies only to auto-pipeline cases. Synthetic cases already have
known, intentional query depths and are exempt from this filter.

Multiple query signals can be generated from a single injection run by picking different
X-carrying bits.

---

## Testcase Generation Flow

```
1. Obtain netlist (ISCAS'85 download; or synthesize from RTL for hand-authored cases)
2. Freeze netlist: compute SHA-256 checksum, store in manifest
   Derive injection seed: seed = int(sha256[:8], 16); record in build.json
3. Generate testbench from template (auto-gen path) or use hand-authored testbench
4. Record build.json: simulator version, all -D defines, library files, compilation flags
5. Run probe simulation (no injection) → probe VCD
6. Find T_inject = find_injection_time(probe_vcd, probe_limit)
   — If None (design never fully clean within window): reject design
7. Scan signal hierarchy → pick up to 5 injection targets using SHA-derived seed
   (exclude clocks, power, scan, zero-fanout signals)
8. For each injection target:
   a. Compile with injection at T_inject
   b. Run injection simulation → sim.vcd
   c. Compile without injection block (same testbench, defines, libraries)
   d. Run no-injection simulation → sim_no_inject.vcd
   e. Validate: Layers 1–6 (see below); Layer 6 uses both VCDs
   f. Scan sim.vcd for candidate query signals:
      — all (signal, bit) pairs X after T_inject AND not X at same time in no-injection VCD
      — apply query filters (see Signal Hierarchy Scanner)
   g. Determine query time per signal type:
      — synchronous: N * clock_period + half_period
      — asynchronous reset: first observed X time in injection VCD for the query signal
      — combinational: T_inject + 20
   h. Store manifest: injection_target (gate-level signal[bit]), injection_time,
      query_signal (signal[bit]), query_time, max_output, SHA-256, sim_env, timing fields,
      no_inject_vcd filename
9. Append to registry.json (append-only; existing entries never modified)
```

One probe simulation per netlist; multiple injection targets and query signals can be
generated from the same probe result.

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
          — FAIL → design rejected; error categorized as primary-input (testbench-fixable)
            or internal-signal (cell model / design issue; reject from automated pipeline;
            do not attempt $deposit on internal signals as a fix)

[Layer 3] Queried signal is X at query time
          — confirms X actually reached the query point
          — FAIL → injection didn't propagate, discard testcase

[Layer 4] Injection target is X in VCD at injection time
          — confirms force/deposit took effect
          — for $deposit: verify X persisted for at least 2 clock cycles
          — FAIL → testbench bug

[Layer 5] Manifest schema lint
          — non-negative times, injection_target and query_signal are valid "signal[bit]"
            strings present in the elaborated hierarchy; injection_class present;
            max_output present and positive
          — FAIL → rejected

[Layer 6] Counterfactual check: simulation without injection
          — run identical simulation with injection block removed → sim_no_inject.vcd
          — verify query signal is NOT X at query time in no-injection run
          — retain sim_no_inject.vcd; store path in manifest as "no_inject_vcd"
          — FAIL → independent X source at query signal exists; testcase discarded
```

Layer 6 produces `sim_no_inject.vcd`, which is retained in the testcase directory and
referenced in the manifest. This VCD is used at grading time for the per-time independence
check in `grade()`.

**Layer 2 implementation:**

```python
def contains_unknown(value: str) -> bool:
    """True if VCD value contains any X or Z bit."""
    v = value.lower().lstrip('b')
    return any(c in ('x', 'z') for c in v)

def validate_clean_sim(vcd: VCDDatabase, injection_time: int, netlist: NetlistGraph):
    for sig in vcd.all_signals():
        # Check initial value (before any transition at t=0)
        initial = vcd.get_initial_value(sig)
        if initial is not None and contains_unknown(initial):
            if netlist.is_primary_input(sig):
                raise CleanEnvError(
                    f"DIRTY ENV: {sig} starts as {initial!r} (primary input). "
                    f"Fix: drive {sig} to a known value in the testbench initial block."
                )
            else:
                raise CleanEnvError(
                    f"DIRTY ENV: {sig} starts as {initial!r} (internal signal). "
                    f"This may indicate an uninitialized FF or pessimistic cell model. "
                    f"This design is not suitable for the automated pipeline."
                )
        # Check all transitions before injection time
        for (t, v) in vcd.get_transitions(sig):
            if t >= injection_time:
                break
            if contains_unknown(v):
                if netlist.is_primary_input(sig):
                    raise CleanEnvError(
                        f"DIRTY ENV: {sig} = {v!r} at t={t} (primary input). "
                        f"Fix: ensure {sig} is driven before simulation starts."
                    )
                else:
                    raise CleanEnvError(
                        f"DIRTY ENV: {sig} = {v!r} at t={t} (internal signal). "
                        f"This design is not suitable for the automated pipeline."
                    )
```

The VCD parser must expose `get_initial_value()`. If the parser does not support this, it
is not suitable for Layer 2.

---

## Golden Promotion Criteria

A testcase is promoted to `status: "golden"` iff it passes **all** of the following:

1. **Layers 1–6** of the validation pipeline pass (including Layer 6 producing
   `sim_no_inject.vcd`)
2. **X propagated:** at least one `(signal, bit)` pair other than the injection target is
   X in the injection VCD after `T_inject` and not X at the same time in the no-injection
   VCD — the injection caused observable, injection-caused X propagation.
3. **Manifest is complete:** all required fields present and schema-valid (Layer 5),
   including `expected.max_output`

"Golden" is a property of the testcase, established without running the tracer under test.
The grading rule (see Tracer Evaluation Oracle above) is applied separately when evaluating
a tracer implementation against the corpus.

**Black-box cases:** For testcases in the `structural/black_box/` category, the structural
path check in `grade()` stops at the black-box boundary. The oracle accepts any X-carrying
input at the black-box boundary that has a structural path (in the netlist graph, treating
the black box as a combinational pass-through for path existence purposes) to the query
signal. Testing inferences about black-box internals is explicitly out of scope.
