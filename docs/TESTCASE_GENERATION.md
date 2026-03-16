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

`cone_members` is therefore computed dynamically from the VCD after simulation:

```python
cone_members = {
    sig
    for sig in vcd.all_signals()
    if vcd.get_first_x_time(sig, after=injection_time) is not None
}
```

This is correct for both combinational and sequential circuits:
- **Combinational:** equivalent to static cone traversal — every signal reachable from the
  injection point through combinational logic will appear X in the VCD.
- **Sequential:** only FFs that actually captured X at a clock edge are included. FFs in
  the static cone that never saw X (wrong clock phase, enable low, etc.) are excluded.

Since Layers 2 and 6 guarantee the injection is the only X source, any signal that is X in
the VCD after injection time is definitively caused by the injection.

Membership is at bus-signal granularity: `foo[7:0]` and `foo[3]` are both represented as
`foo` in `cone_members`. `cone_members` is a set of signal-name strings with no time
dimension.

`cone_members` is computed from the VCD post-simulation and stored in the manifest.

### Timing condition

For a signal S reported by the tracer at time T, the timing check is:

```
first_x_time(S) ≤ T ≤ first_x_time(S) + clock_period_ticks
```

where `first_x_time(S)` = the earliest VCD timestamp at which S transitions to X at or
after `injection_time`.

### Grading rule

A tracer output passes a testcase iff **all three** of the following hold:

1. **Root cause reached:** the injection target is in `tracer_output` — the tracer traced
   all the way back to the source, including through reconvergent paths.
2. **Precision:** `tracer_output ⊆ cone_members` — no reported signal is outside the cone;
   no fabricated paths.
3. **Focus:** `|tracer_output| ≤ 5` — the tracer returns a focused answer, not a dump of
   the entire VCD.

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
10. Compute cone_members: scan VCD for all signals that become X after injection_time
11. Compute cone_depth: count of distinct X-carrying signals between injection target and
    query signal along the shortest VCD-observed path; verify cone_depth ≥ 3
12. Compute sequential_depth: number of clock-edge boundaries X crossed on the path from
    injection target to query signal (0 for purely combinational testcases)
13. Store manifest with cone_members, cone_depth, sequential_depth, SHA-256, sim_env,
    timing fields
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
2. **Cone computation succeeds:** `cone_members` is computed from the VCD and is non-empty
   (at least the injection target and query signal are X after injection time).
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
def grade(tracer_output, manifest):
    injection_target = manifest["x_injection"]["target"]
    cone = set(manifest["expected"]["cone_members"])
    signals_reported = {sig for sig, t in tracer_output}

    # Root cause: tracer must reach the injection point
    # This applies equally to direct paths and reconvergent fanout — all paths
    # lead back to the same injection point, so the tracer must find it.
    if injection_target not in signals_reported:
        return FAIL, f"Tracer did not reach injection point {injection_target!r}"

    # Precision: no signal outside the cone — no fabricated paths
    if not signals_reported.issubset(cone):
        return FAIL, f"Signals outside cone: {signals_reported - cone}"

    # Focus: bounded output size
    if len(tracer_output) > 5:
        return FAIL, f"Tracer returned {len(tracer_output)} results; maximum is 5"

    # Timing: injection target must be reported at a plausible time
    inj_time = manifest["x_injection"]["time"]
    period = manifest["timing"]["clock_period_ticks"]
    for sig, t in tracer_output:
        if sig == injection_target:
            first_x = vcd.get_first_x_time(sig, after=inj_time)
            if first_x is not None and abs(t - first_x) <= period:
                return PASS, f"Correctly reached injection target {injection_target!r} at t={t}"

    return FAIL, f"Injection target {injection_target!r} reported at wrong time"
```

**Black-box cases:** For a signal at a black-box input boundary, `first_x_time` is the
time at which that input transitioned to X. Reporting any X-carrying black-box input on
the path from injection to query is a valid answer. The oracle accepts observability-limit
answers; testing inferences about black-box internals is not possible without knowing
those internals and is explicitly out of scope.
