# X-Tracer Testcase Generation Plan

## Motivation

### Why testcases first

X-tracing semantics are subtle. The correct answer for a given query depends on gate-level X-propagation rules, sequential capture timing, reconvergent fanout, and the interaction of all three. Bugs in the tracer's logic are easy to introduce and hard to spot by code review alone — a wrong answer looks plausible.

Building the testcase corpus before the tracer implementation means:
- Every module is developed against a concrete pass/fail signal from day one
- Regressions are caught immediately as modules are integrated
- Agents working on the tracer have unambiguous ground truth to code against, not just a spec document

Without this, the risk is that the tracer is "working" against hand-waved examples and only fails on real designs when it is much harder to debug.

### Why explicit X injection

The naive approach to generating testcases is to simulate a design, find a signal that happens to be X in the VCD, and then derive the expected root cause by tracing through the netlist manually or with a reference simulator. This has two serious problems:

1. **Deriving the expected answer is as hard as writing the tracer itself.** A reference simulator that correctly handles all gate types, sequential elements, UDPs, and multi-driver resolution is a substantial project in its own right — effectively building the tool twice.

2. **X can arise from many simultaneous sources** in a real simulation (uninitialized registers, undriven inputs, simulator pessimism), making the "correct" root cause ambiguous and the expected answer difficult to specify precisely.

Explicit X injection avoids both problems. By ensuring the simulation environment is completely clean before injection — all inputs driven, all registers initialized — the injection point is by construction the only possible root cause. The expected answer writes itself. No reference simulator is needed at any stage.

### Why open-source netlists

Hand-authored small netlists are necessary for targeted unit testing of specific gate types and scenarios, but they cannot cover the structural complexity of real designs: deep reconvergent cones, realistic sequential depths, mixed cell libraries, and unusual but legal Verilog constructs. Open-source netlists from the ISCAS benchmark suite, RISC-V cores, and SkyWater tapeouts provide this coverage without requiring access to proprietary designs. The ISCAS benchmarks have the additional advantage that their fault analysis properties are extensively published, providing an independent cross-check on testcase correctness.

---

## Core Principle: Explicit X Injection

The only source of X in any testcase simulation is an explicitly injected X via `force` or `$deposit`. This means:
- Any signal that is X in the VCD is trivially in the backward cone of the injection point
- The expected root cause is always the injection point — no derivation needed
- No reference simulator is required at any stage

---

## Open-Source Netlist Sources

### Tier 1: Ready to use (already gate-level Verilog)

**ISCAS'85 / ISCAS'89** — highest priority starting point
- ISCAS'85: pure combinational, 5–2600 gates — ideal for gate model validation
- ISCAS'89: sequential with DFFs, up to 250K gates — ideal for flop/latch X-tracing
- **Key advantage:** correct answers are published in academic fault analysis literature
- Sources: `github.com/jpsety/verilog_benchmark_circuits`, `github.com/santoshsmalagi/Benchmarks`

**ITC'99** — medium scale, already synthesized with Synopsys DC
- 29–70K gates, both combinational and sequential variants
- Synthesized gate-level netlists included — no extra synthesis step
- Source: `github.com/cad-polito-it/I99T`, CC licensed

**HDL Benchmarks (TrustworthyComputing)** — RTL + Yosys-synthesized netlists paired
- Fast to onboard; netlists already generated
- Source: `github.com/TrustworthyComputing/hdl-benchmarks`

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

### Tier 3: Real tapeout netlists (SkyWater 130nm)

**Caravel / SkyWater PDK designs**
- Uses `sky130_fd_sc_hd__*` standard cells — validates cell library mapping handles real vendor cell names
- Generated by OpenLane/Yosys — realistic tool-output format
- Source: `github.com/efabless/caravel`, Apache 2.0

---

## Testcase Corpus Structure

```
tests/
├── cases/
│   ├── combinational/      # Agent A
│   │   ├── and_x_prop/
│   │   ├── or_masking/
│   │   ├── mux_select_x/
│   │   └── reconvergent/
│   ├── sequential/         # Agent B
│   │   ├── flop_uninit/
│   │   ├── latch_enable_x/
│   │   └── reset_x/
│   ├── structural/         # Agent C
│   │   ├── undriven_net/
│   │   ├── black_box/
│   │   └── multi_driver/
│   └── stress/             # Agent D
│       ├── deep_cone/
│       ├── wide_reconvergence/
│       └── large_synthetic/
├── registry.json           # Merged index of all cases (append-only)
└── schema.json             # Manifest schema (read-only)
```

### Coverage Matrix

| Agent | Category | Recommended Source | Target count |
|-------|----------|--------------------|-------------|
| Agent A | combinational/* | ISCAS'85 (c17, c432, c880) | 20 golden |
| Agent B | sequential/* | ISCAS'89 (s27, s386, s1423), ITC'99 | 15 golden |
| Agent C | structural/* | ITC'99 edge cases, hand-authored | 10 golden |
| Agent D | stress/* | EPFL multiplier, CVA6, PicoRV32 | 5 large |
| Correctness agent | regression suite | ISCAS'85 (cross-check published fault analysis) | all |

---

## Manifest Schema

Every testcase has a `manifest.json`:

```json
{
  "id": "seq_deposit_uninit_ff_001",
  "category": "sequential",
  "verilog": "netlist.v",
  "vcd": "sim.vcd",
  "testbench": "tb.v",
  "query": {
    "signal": "top.u_core.result[3]",
    "time": 150
  },
  "x_injection": {
    "method": "deposit",
    "target": "top.u_core.u_alu.acc_reg",
    "value": "8'bx",
    "time": 0
  },
  "expected": {
    "root_cause_class": "uninit_ff",
    "trace_endpoint": "top.u_core.u_alu.acc_reg",
    "injection_time": 0
  },
  "status": "golden",
  "author": "agent-B"
}
```

Valid `root_cause_class` values: `primary_input`, `uninit_ff`, `x_propagation`, `control_x`, `undriven_net`, `black_box_output`.

### X Injection Methods

| Method | Verilog | Root Cause Class |
|--------|---------|-----------------|
| `force` on primary input | `force top.a = 1'bx;` | `primary_input` |
| `$deposit` on FF state | `$deposit(top.u_alu.acc_reg, 8'bx);` | `uninit_ff` |
| `force` on internal net | `force top.u_core.net_42 = 1'bx;` | `x_propagation` |
| `force` on mux select | `force top.u_ctrl.sel = 1'bx;` | `control_x` |
| `force` on reset/enable | `force top.u_pipe.en = 1'bx;` | `control_x` |

---

## Clean Simulation Environment (mandatory)

Before injecting X, the simulation must have zero X values anywhere. This is enforced by the validation pipeline.

**Rule 1: All primary inputs driven with known values**
```verilog
initial begin
    a = 1'b0; b = 1'b1; sel = 1'b0;  // explicit, no implicit Z
end
always #5 clk = ~clk;
```

**Rule 2: All sequential elements initialized via reset**
```verilog
initial begin
    rst_n = 0;
    repeat(8) @(posedge clk);   // hold reset long enough to flush all FFs
    rst_n = 1;
    repeat(16) @(posedge clk);  // settle to clean state — zero X in VCD here
    // NOW inject X
    $deposit(top.u_alu.acc_reg, 8'bx);
end
```

**Rule 3: No reset port — use `$deposit` to pre-initialize all FFs**
```verilog
initial begin
    $deposit(top.u_pipe.stage1, 8'h00);
    $deposit(top.u_pipe.stage2, 8'h00);
    // ... all FFs in design
    #1;
    // begin stimulus
end
```

**Rule 4:** No tristates left floating — pull all inout ports to a known value.

**Rule 5:** Deterministic stimulus only — no `$random` without a fixed seed.

---

## Testbench Handling for Downloaded Netlists

Downloaded netlists fall into two cases:

```
Does a testbench exist?
  ├── No  → Auto-generate one
  └── Yes → Wrap it with runtime cap + injection hook
```

### Case 1: No Testbench — Auto-Generate

Parse the top-level module ports using `pyslang`, classify them, emit a standard template.

**Port classification heuristics:**

| Port | Heuristic |
|------|-----------|
| Clock | name matches `/clk\|clock\|ck/i`, 1-bit input |
| Reset | name matches `/rst\|reset\|rstn\|rst_n/i`, 1-bit input |
| Data input | all remaining inputs |
| Output | all outputs (not driven by testbench) |

**Generated testbench template:**
```verilog
`timescale 1ns/1ps
module tb;
  // --- port declarations (filled from netlist port list) ---
  reg clk, rst_n;
  reg [W-1:0] data_in;  // one per data input port

  // --- DUT instantiation ---
  top_module dut (.clk(clk), .rst_n(rst_n), .in(data_in), ...);

  // --- VCD dump ---
  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  // --- Clock ---
  initial clk = 0;
  always #5 clk = ~clk;

  // --- Stimulus: reset then drive known values ---
  initial begin
    rst_n = 0;
    data_in = 0;
    repeat(8) @(posedge clk);
    rst_n = 1;
    repeat(16) @(posedge clk);  // settle to clean state
    // --- INJECTION POINT (filled by harness via -D defines) ---
    `ifdef INJECT_FORCE
      force `INJECT_TARGET = `INJECT_VALUE;
    `elsif INJECT_DEPOSIT
      $deposit(`INJECT_TARGET, `INJECT_VALUE);
    `endif
    repeat(32) @(posedge clk);  // let X propagate
    $finish;
  end

  // --- Hard timeout ---
  initial #`SIM_TIMEOUT $finish;
endmodule
```

The harness fills `INJECT_TARGET`, `INJECT_VALUE`, and `SIM_TIMEOUT` via `-D` defines passed to `iverilog`.

**No-reset fallback:** If no reset port is detected, the harness pre-initializes all FFs to 0 via `$deposit` calls using the full signal list from the hierarchy scanner.

### Case 2: Testbench Exists — Wrap With Runtime Cap and Injection Hook

Never modify the original testbench. Compile a wrapper alongside it:

```verilog
// tb_wrapper.v — compiled alongside original tb
// Hard timeout — kills simulation regardless of original tb $finish
initial #`SIM_TIMEOUT begin
  $display("TIMEOUT at %0t", `SIM_TIMEOUT);
  $finish;
end

// Injection block — fires after design has had time to initialize
initial begin
  #`INJECT_TIME;
  `ifdef INJECT_FORCE
    force `INJECT_TARGET = `INJECT_VALUE;
  `elsif INJECT_DEPOSIT
    $deposit(`INJECT_TARGET, `INJECT_VALUE);
  `endif
end
```

**Determining `INJECT_TIME`:** Run a short probe simulation (no injection, hard timeout at `PROBE_LIMIT`). Scan the resulting VCD for the earliest time at which all signals have settled to non-X values. Use that as `INJECT_TIME`.

**Setting `SIM_TIMEOUT`:**
```
SIM_TIMEOUT = INJECT_TIME + (N_PROPAGATION_CYCLES * CLOCK_PERIOD)
```
Default `N_PROPAGATION_CYCLES = 64`. Enough for X to traverse any realistic sequential depth.

---

## Signal Hierarchy Scanner

Used to enumerate candidate injection targets for downloaded netlists.

```python
def scan_injection_candidates(netlist: NetlistGraph) -> list[InjectionCandidate]:
    candidates = []
    for signal in netlist.all_signals():
        if is_clock(signal):         continue  # forcing clk to X causes chaos
        if is_reset(signal):         continue  # skip unless testing reset X specifically
        if is_power_ground(signal):  continue  # VDD/VSS/VDDIO etc.

        fanout = len(netlist.get_fanout(signal))
        if fanout == 0: continue  # X won't propagate anywhere useful

        candidates.append(InjectionCandidate(
            signal=signal,
            fanout=fanout,
            is_ff_output=netlist.get_driver(signal).type in SEQUENTIAL_TYPES,
        ))

    # Prefer FF outputs (interesting sequential cases) and high fanout
    candidates.sort(key=lambda c: (c.is_ff_output, c.fanout), reverse=True)
    return candidates
```

**Clock/reset detection** uses name heuristics plus structural checks (a clock signal typically fans out to many FF clock ports).

**Selection strategy:** Pick 5 injection targets per netlist spread across the candidate list:
- 1 high-fanout combinational net
- 1 low-fanout combinational net
- 1 FF output (sequential depth)
- 1 mux select or enable
- 1 randomly sampled

This maximises diversity from a single netlist without redundant simulation runs.

---

## Testcase Generation Flow

One simulation run can produce many testcases — one per X-carrying signal:

```
1. Obtain netlist (download or synthesize from RTL)
2. Scan signal hierarchy → candidate injection targets
3. Select injection point
4. Generate or wrap testbench (runtime cap applied)
5. Run probe simulation → determine INJECT_TIME (existing tb only)
6. Run simulation with injection → VCD
7. Validate: zero X before injection time
8. Scan VCD after injection: collect all signals that become X
9. Emit one manifest per X-carrying signal (or sampled subset)
   — expected answer is always the injection point
10. Append to registry.json
```

Vary injection points and query signals at different distances (near, mid-cone, far) for diverse coverage.

---

## Validation Pipeline

Every testcase must pass all layers before entering the corpus:

```
[Layer 1] iverilog + slang lint
          — syntax, elaboration, undefined references
          — FAIL → rejected, agent gets error

[Layer 2] Zero X in VCD before injection time
          — confirms clean simulation environment
          — FAIL → testbench rejected (environment not clean)

[Layer 3] Queried signal is X at query time
          — confirms X actually reached the query point
          — FAIL → injection didn't propagate, discard testcase

[Layer 4] Injection target is X in VCD at injection time
          — confirms force/deposit took effect
          — FAIL → testbench bug

[Layer 5] Manifest schema lint
          — valid root_cause_class, non-negative times, signal paths exist
          — FAIL → rejected
```

**Layer 2 implementation:**
```python
def validate_clean_sim(vcd: VCDDatabase, injection_time: int):
    x_before = [
        (sig, t)
        for sig in vcd.all_signals()
        for (t, v) in vcd.get_transitions(sig)
        if t < injection_time and v == 'x'
    ]
    assert not x_before, (
        f"X values found before injection at t={injection_time}:\n"
        + "\n".join(f"  {sig} at t={t}" for sig, t in x_before)
    )
```

Layer 2 failures are always a testbench problem — either an uninitialized FF or an undriven input. The error output lists the offending signals so the agent can fix them.
