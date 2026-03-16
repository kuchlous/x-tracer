# Final Synthesis

## 1. Points Conceded

**From Round 1–2 critiques:**

- **Root-cause taxonomy contradicts the core principle.** `undriven_net` and `black_box_output` are removed as standalone `root_cause_class` values. The schema is split into `injection_class` and an optional `structural_class` annotation.
- **"Expected answer is always the injection point" was an unproven semantic assumption.** Replaced entirely by a cone-membership oracle defined explicitly in this document. The `trace_endpoint` scalar is removed.
- **Layer 2 implementation was technically wrong.** `v == 'x'` misses multi-bit vectors, Z values, and signals that start as X with no prior transition. Replaced with a `contains_unknown()` helper and explicit initial-value checking.
- **Auto-generated testbench heuristics fail silently on scan/test signals, wrong reset polarity, and multi-clock designs.** Scan/test signals (`scan_en`, `test_mode`, `mbist_en`, etc.) are explicitly held at their safe (functional) value. Reset polarity and type must be specified in design metadata; auto-detection is not attempted. Multi-clock designs are out of scope for automated generation.
- **Probe simulation and wrapper mode are under-specified and uncontrollable.** The wrapper mode (Case 2) is eliminated entirely. Downloaded netlists with existing testbenches are either replaced with auto-generated testbenches or classified as requiring hand-authored work. The probe-simulation approach for determining `INJECT_TIME` is dropped.
- **`$deposit` and `force` have different semantics and were conflated.** Injection is restricted to two methods with no overlap: `$deposit` on Verilog `reg` state elements in RTL-level simulations; `force` on module primary inputs with no competing driver in gate-level simulations. `force` is held for the duration of simulation (no competing driver, no release ambiguity). All other injection methods (internal nets, control nets, enables) require hand-authored testbenches.
- **No-reset fallback is not operationally credible for nontrivial netlists.** Replaced by a requirement that any design with sequential elements supply a design-metadata file with full reset specification. Designs lacking this are rejected from automated generation.
- **ISCAS literature cross-check was claimed to validate X-tracing correctness; it does not.** Stuck-at fault analysis does not validate Verilog X-propagation semantics. The claim is removed. The ISCAS benchmarks are retained as netlist sources for their structural properties (known topology, widely characterized connectivity), not as semantic calibration.
- **Manifest was missing `sim_env`, `timescale`, clock period, and query timing fields.** Added. All times are integers in simulator ticks; `timescale` in `sim_env` is the only place physical time appears. `clock_period_ticks` replaces `clock_period_ns` throughout.
- **One simulation producing one testcase per X-carrying signal floods the corpus with correlated cases.** Capped at 5 testcases per simulation run, with explicit diversity requirements on the 5 query signals.
- **Scanner could not identify mux selects or control signals from the code as written.** The "1 mux select or enable" selection category is dropped and replaced with structurally-motivated selection criteria that survive synthesis.
- **Layers 2–4 do not prove sole causality.** The architectural claim "injection is the sole cause" is abandoned. Layer 6 (no-injection counterfactual) is added.
- **ISCAS'89 and ITC'99 were marketed as sequential automated targets, but gate-level injection is now restricted to primary inputs only, making them effectively combinational-only targets.** ISCAS'89 is dropped from the automated pipeline. Gate-level automated targets are ISCAS'85 only (purely combinational — no mismatch). Sequential coverage comes from hand-authored testbenches.
- **The semantics document was deferred to a future deliverable.** The oracle is defined explicitly in this document. No external document is required before corpus generation.
- **Timing schema used mixed units** (some fields in ns, some in ticks, some unitless). All time fields in the manifest are integers in simulator ticks uniformly.
- **Top-module hierarchical paths were unstable and assumed a literal `top` instance name.** All auto-generated testbenches instantiate the DUT as `dut`; all manifest paths are rooted at `tb.dut`. Netlists are frozen by SHA-256 checksum; toolchain drift creates new testcases, not updates to existing ones.
- **The corpus taxonomy overpromised what restricted generation can produce.** `multi_driver` and `undriven_net` are removed as automated targets. The taxonomy is collapsed to: automated combinational (ISCAS'85), hand-authored sequential and structural.
- **No concrete acceptance rule for "golden" was defined.** Defined now: Layers 1–6 plus cone-membership pre-computation plus a minimum cone-depth requirement.

**From Round 5 (final) critiques:**

- **The golden-promotion rule was circular** — it depended on running the tracer under test, which conflates corpus quality (golden) with tracer evaluation (pass/fail). Decoupled: "golden" means validation pipeline Layers 1–6 pass and `cone_members` is computed and stored. Tracer evaluation against the corpus is a separate step.
- **The cone-membership oracle was too weak** — a tracer that returns every signal ever X in the design would pass. Added a precision constraint: the tracer's output must satisfy `tracer_output ⊆ cone_members` AND `|tracer_output| ≤ 5`. This rejects "dump everything" strategies while permitting any focused answer in the cone.
- **The oracle terminology was internally confused** ("ancestor" and "forward cone" mixed). Replaced with a precise definition: S ∈ `cone_members` iff `injection_target` can reach S **and** S can reach `query_signal` in the static directed netlist graph.
- **The timing window `[injection_time, query_time]` was too broad**, accepting a node that was briefly X at an irrelevant early time. Tightened: the reported time T for signal S must be within one clock period of `first_x_time(S)`, defined as the earliest VCD transition of S to X after `injection_time`.
- **The selection strategy still referenced deep sequential traversal, inconsistent with the ISCAS'85-only automated scope.** Selection strategy updated to match the actual automated corpus (purely combinational benchmarks).
- **Manual testcases were left with an undefined oracle.** All testcases — automated and manual — use the same cone-membership oracle with the same grading rules. Manual authors compute and provide `cone_members`.
- **"Bit-identical VCD" was asserted, not established.** Weakened: the auto-generated testbench is deterministic by construction (fixed seed, no external files, no plusargs); VCDs are reproducible in semantic content. Bit-level identity across simulator versions is not guaranteed and is not required.
- **`cone_members ≥ 2` is a fake quality gate** — a buffer between injection and query satisfies it. Minimum cone depth raised: there must be at least 2 intermediate signals between injection target and query signal (cone depth ≥ 3 counting endpoints).
- **`cone_members` was under-specified regarding bit-select granularity and time dimension.** Specified: membership is at bus-signal granularity (signal name without subscript); there is no time dimension in `cone_members`; it is a set of signal name strings.
- **The automated scope contradiction between "ISCAS'85 only" and "simple sequential"** in the same document. Clarified uniformly: the automated pipeline produces combinational testcases only. "Simple sequential" is removed from the automated scope description.

---

## 2. Points Rejected

**R5.4 — Static cone ignores sensitization, masking, and time alignment.**
The alternative — dynamic sensitization analysis — is essentially reimplementing the tracer under test. The static cone is the most powerful mechanically-computable oracle available without building a reference tool. False positives (cone members that were briefly X but causally irrelevant to the query) are an accepted and documented limitation. The oracle still rejects tracers that report signals outside the cone entirely, which is the failure mode that matters.

**R5.6 — Behaviorally sterile simulations undermine the corpus.**
The corpus tests a tracing algorithm, not a design. The tracer's input is a netlist graph and a VCD. The question the corpus answers is: "given this netlist structure and these X values in the VCD, does the tracer identify a valid backward path?" For that question, constant-stimulus simulations produce real X propagation through real netlist structure. Whether the design was in a realistic protocol state is irrelevant to whether the tracer traverses the cone correctly. This objection would be valid if the corpus were testing simulation coverage; it is not.

**R5.10 — Freezing netlists by checksum makes the corpus brittle and non-maintainable.**
A regression corpus must be stable. The purpose of the corpus is to detect tracer regressions, not to track synthesis evolution. When a netlist is regenerated with a new tool version, the resulting testcase is new and appended; the old testcase remains valid and continues to catch regressions in the tracer against the original netlist. The corpus grows; correctness is not retroactively invalidated. This is the correct tradeoff.

**R5.11 — Black-box handling guts black-box-specific validation.**
The cone-membership oracle correctly handles what is observable at the netlist level: the last visible X-carrying signal on the path to a black-box boundary is a valid answer. Testing whether the tracer makes correct inferences about internal black-box behavior requires knowing the box's internals — which by definition are unavailable. The limitation is documented explicitly. The corpus validates that the tracer correctly stops at the observable boundary; it cannot test reasoning about opaque internals.

**R5.14 — Claim that the original testbench is irrelevant is unsupported.**
For the restricted automated scope — ISCAS'85 combinational benchmarks with primary-input injection — this claim holds. ISCAS'85 circuits are combinational; they have no protocol modes, no state machines, and no operating regimes. Driving inputs to known constant values and injecting X at a primary input produces valid X propagation through the full combinational cone. The claim is not made for Tier 2/3 designs, where it would not hold.

---

## 3. Updated Document

```markdown
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
injection point is by construction the origin of every X observed in the VCD. The
cone-membership oracle (see below) can then be computed mechanically from the netlist
graph and VCD without any reference simulator.

### Why open-source netlists

Hand-authored small netlists are necessary for targeted unit testing of specific gate types
and scenarios, but they cannot cover the structural complexity of real designs: deep
reconvergent cones, realistic sequential depths, mixed cell libraries, and unusual but legal
Verilog constructs. Open-source netlists from the ISCAS benchmark suite, RISC-V cores, and
SkyWater tapeouts provide this coverage without requiring access to proprietary designs.

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
- The cone-membership oracle can be applied without ambiguity
- No reference simulator is required for automated testcases

**Sole causality is not claimed.** A primary input that feeds control logic can produce
multiple independent effects. The corpus does not assert that the injection is the *only*
cause of observed X values; it asserts that the injection is *a* cause that lies on a
verifiable path to the query signal. The oracle is designed to be checkable under this
weaker condition (see Tracer Evaluation Oracle).

---

## Tracer Evaluation Oracle

This section defines the oracle used to grade tracer outputs against the corpus. This
definition is authoritative; no separate semantics document is required for automated
testcases.

### Cone membership

For a testcase with injection target `I` and query signal `Q`:

```
cone_members = {S : I →* S in the static netlist graph AND S →* Q in the static netlist graph}
```

Where `→*` means "can reach via directed edges in the gate-level netlist" (combinational
data edges, FF Q→D edges through capture, and module port crossings). Both `I` and `Q` are
included in `cone_members`.

Membership is at bus-signal granularity: `foo[7:0]` and `foo[3]` are both represented as
`foo` in `cone_members`. There is no time dimension in the set; `cone_members` is a set of
signal-name strings.

`cone_members` is pre-computed from the frozen netlist at testcase generation time and
stored in the manifest.

### Timing condition

For a signal S reported by the tracer at time T, the timing check is:

```
first_x_time(S) ≤ T ≤ first_x_time(S) + clock_period_ticks
```

where `first_x_time(S)` = the earliest VCD timestamp at which S transitions to X at or
after `injection_time`.

### Grading rule

A tracer output passes a testcase iff **all three** of the following hold:

1. **Coverage:** `tracer_output ∩ cone_members ≠ ∅` — at least one reported signal is in
   the cone.
2. **Precision:** `tracer_output ⊆ cone_members` — no reported signal is outside the cone.
3. **Focus:** `|tracer_output| ≤ 5` — the tracer returns a focused answer, not a dump of
   the entire VCD.

The timing condition applies to at least one element satisfying condition 1.

**Accepted limitation:** The static cone does not account for sensitization or masking. A
signal may be in `cone_members` and carry X in the VCD without being the dominant causal
contributor to the query. The oracle accepts any signal that is both structurally on a path
and dynamically X in the VCD. Distinguishing dominant from subsidiary causes requires
dynamic analysis equivalent to reimplementing the tracer, and is out of scope for this
corpus.

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

## Testcase Corpus Structure

```
tests/
├── cases/
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
│       ├── wide_reconvergence/
│       └── large_synthetic/
├── registry.json           # Merged index of all cases (append-only)
└── schema.json             # Manifest schema (read-only)
```

The registry distinguishes `"generation": "auto-pipeline"` from `"generation": "manual"`.
Coverage metrics are reported separately for each category. The automated pipeline makes no
claim about `sequential/` or `structural/` coverage.

### Coverage Matrix

| Agent | Category | Generation | Source | Target count |
|-------|----------|------------|--------|-------------|
| Agent A | combinational/* | Automated | ISCAS'85 (c17, c432, c880, c2670) | 20 golden |
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
    "oracle": "cone_membership_v1",
    "injection_target": "tb.dut.a",
    "injection_time": 80,
    "query_signal": "tb.dut.G49",
    "query_time": 150,
    "cone_members": ["tb.dut.a", "tb.dut.G7", "tb.dut.G11", "tb.dut.G49"]
  },
  "cone_depth": 3,
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
            cone_depth_to_output=netlist.shortest_path_to_any_output(signal),
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
10. Compute cone_members: static netlist analysis, signal-level granularity
11. Verify cone_depth ≥ 3 (injection target + ≥2 intermediate signals + query signal)
12. Store manifest with cone_members, cone_depth, SHA-256, sim_env, timing fields
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
            hierarchy, cone_members is non-empty, cone_depth ≥ 3
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
2. **Cone pre-computation succeeds:** `cone_members` is computed from the static netlist
   graph and is non-empty
3. **Minimum cone depth:** `cone_depth ≥ 3` — the cone contains the injection target,
   at least 2 intermediate signals, and the query signal. Testcases where injection
   directly drives the query with no intermediate logic are rejected (no traversal
   exercise).
4. **Manifests is complete:** all required fields present and schema-valid (Layer 5)

"Golden" is a property of the testcase, established without running the tracer under test.
The grading oracle (cone membership check) is applied separately when evaluating a tracer
implementation against the corpus.

### Grading rule (applied during tracer evaluation, not during corpus construction)

Given a tracer's output `T_out` = set of `(signal, time)` pairs for a given testcase:

```python
def grade(tracer_output, manifest):
    cone = set(manifest["expected"]["cone_members"])
    signals_reported = {sig for sig, t in tracer_output}
    times_reported = {(sig, t) for sig, t in tracer_output}

    # Precision: no signal outside the cone
    if not signals_reported.issubset(cone):
        return FAIL, f"Reported signals outside cone: {signals_reported - cone}"

    # Focus: bounded output size
    if len(tracer_output) > 5:
        return FAIL, f"Tracer returned {len(tracer_output)} results; maximum is 5"

    # Coverage: at least one valid (signal, time) pair
    inj_time = manifest["x_injection"]["time"]
    period = manifest["timing"]["clock_period_ticks"]
    for sig, t in tracer_output:
        first_x = vcd.get_first_x_time(sig, after=inj_time)
        if first_x is not None and abs(t - first_x) <= period:
            return PASS, f"Valid answer: {sig} at t={t}"

    return FAIL, "No reported (signal, time) pair satisfies the timing condition"
```

**Black-box cases:** For a signal at a black-box input boundary, `first_x_time` is the
time at which that input transitioned to X. Reporting any X-carrying black-box input on
the path from injection to query is a valid answer. The oracle accepts observability-limit
answers; testing inferences about black-box internals is not possible without knowing
those internals and is explicitly out of scope.
```
