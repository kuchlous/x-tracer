# Round 3 — Claude

## Round 3 Defense

---

**1. "Known cause" destroyed the oracle. CONCEDE — and the Round 2 fix was wrong.**

The Round 2 response made the wrong move. "Known cause" is not a weaker oracle — it is no oracle at all. The critique is exactly right.

The correct fix is the opposite direction: tighten testcase generation until sole causality holds by construction again, rather than weaken the grading criterion. Specifically:

- **Restrict injection to two methods only:** `$deposit` on RTL-level FF state registers, and `force` on module primary inputs with no competing driver.
- Both methods have clean sole-causality properties: `$deposit` on a storage element doesn't alter combinational scheduling; `force` on an undriven primary input has no competing driver to create interaction effects.
- Every other injection method (`force` on internal nets, control nets, enables) is removed from the automated pipeline. Those cases require hand-authored testbenches where a human confirms causality.

This eliminates critiques 1, 3, 4, 6, and 9 in one structural decision. The "known cause" language is retracted. The oracle is "injection is the sole cause" and it holds because the two permitted methods cannot create secondary X sources by construction.

---

**2. `tracing_policy` is a label, not a semantics definition. CONCEDE.**

A version string is not a spec. The manifest cannot define the tracing policy; a separate normative document must exist first, and the manifest references it.

Fix: the `tracing_policy` field in the manifest is replaced with a pointer to a semantics document that defines, at minimum:
- The answer type: a `(signal_path, time_ticks)` pair representing the earliest capture event on the backward trace from the query
- Stopping criterion: stop at the first sequential capture boundary working backward in simulation time from the query event
- Multi-parent ranking: when multiple signals cause the same X, report all; the manifest's `expected` becomes a list, not a scalar
- Mux select masking: a mux select that is X causes the output to be X regardless of data; the trace must follow the select, not the data path, when the select is X

This document is a prerequisite deliverable. No testcases are generated until it exists. The manifest schema is written against it, not before it.

---

**3. Layer 6 counterfactual misses interaction bugs. CONCEDE — but this is now moot.**

The arbitration-change scenario requires `force` on a control net. That method is removed (see point 1). `$deposit` on FF state and `force` on primary inputs do not alter arbitration or scheduling in ways that could create secondary X sources. Layer 6 can remain as a defense-in-depth check but its failure mode is eliminated by the injection restriction.

---

**4. Static cone heuristic is invalid for dynamic X semantics. CONCEDE — and also moot.**

The contamination-detection heuristic from Round 2 is dropped entirely. It was attempting to solve a problem that the injection restriction from point 1 eliminates. Static cone analysis is not used for causality validation in the pipeline.

---

**5. Wrapper strategy cannot control existing testbench scheduling. CONCEDE.**

A wrapper compiled alongside an existing testbench does not own `$finish`, `$dumpvars`, or injection timing relative to the bench's internal state. This is not fixable.

Fix: the "Case 2: Testbench Exists" mode is eliminated. Downloaded netlists with existing testbenches fall into one of two paths:
- If the testbench is simple enough that the auto-generation heuristics can replace it, discard the original and auto-generate.
- If the design requires a preserved testbench (complex protocol environment, memory models, etc.), it is classified as requiring a hand-authored testbench and is out of scope for automated generation.

The probe-simulation approach is also dropped. `INJECT_TIME` is determined from the reset settling logic of the auto-generated testbench only.

---

**6. `query_nba` is unobservable in VCD. CONCEDE.**

The field is dropped. VCD records post-NBA values by simulator convention; there is no per-signal NBA annotation available. The manifest specifies query time in simulator ticks. Queries are always placed at `N * clock_period_ticks + half_period_ticks` — between rising edges — where no active NBA updates should be in flight. This is documented as a convention, not a per-testcase assertion.

---

**7. Reset-polarity retry conflates known values with correct reset. CONCEDE.**

"Non-X after reset" is not a valid reset-detection criterion for the reasons given. The retry heuristic is dropped.

Fix: reset polarity must be specified as a metadata field alongside the downloaded netlist, not inferred at generation time. If it is not specified, the design is rejected from auto-generation. The ISCAS and ITC netlists have known reset conventions; they are documented. Tier 2/3 designs require explicit metadata.

---

**8. Multi-clock designs cannot be handled by the auto-generation pipeline. CONCEDE.**

Single absolute times are not meaningful oracle values in multi-clock designs without domain assignment. Multi-clock designs are explicitly out of scope for the automated pipeline. They require hand-authored testbenches. The coverage matrix is updated to reflect this: Tier 2/3 netlists are used only for hand-authored testcases, not automated generation. The "log a warning" language is removed.

---

**9. force/release timing is arbitrary. MOOT — see point 1.**

`force` on internal nets and control nets is eliminated. The only remaining `force` use is on primary inputs, which are held X for the duration of the simulation (no competing driver, no release needed, no release ambiguity). `$deposit` on FF state is a one-time initialization that propagates forward as simulation runs normally.

---

**10. `$deposit` target not operationally defined on gate netlists. CONCEDE — and scope accordingly.**

The critique is correct: standard-cell flops do not expose a writable state variable in gate-level simulations. `$deposit` on gate-level netlists is not reliable.

Fix: the injection method split follows the netlist level:
- **RTL-level simulations:** `$deposit` on Verilog `reg` state elements (reliable, unambiguous).
- **Gate-level simulations:** `force` on primary input ports only (no competing driver, works on any flattened netlist).

Gate-level netlists (ISCAS, ITC, Sky130) use primary-input injection only. RTL-level designs (PicoRV32, Ibex before synthesis) use `$deposit`. This removes the ambiguity entirely. The manifest records `netlist_level: rtl | gate` and the valid injection methods are gated on that field.

---

**11. Control signal classification doesn't survive synthesis. CONCEDE.**

`get_port_function()` cannot identify mux selects or enables in synthesized netlists because Yosys and DC lower them to gates. The "1 mux select or enable" selection category is dropped.

Fix: the five injection targets per netlist are selected by structural properties that survive synthesis:
1. Highest-fanout combinational net
2. Lowest-fanout combinational net with fanout > 1
3. FF output (primary Q pin in gate-level; reg in RTL)
4. Module primary input
5. Randomly sampled net from the backward cone of the highest-fanout target at cone-depth 3–7

These are structurally identifiable from any netlist level without port-function metadata.

---

**12. Reproducibility still missing stimulus trace. COUNTER-ARGUMENT — partially.**

The critique identifies missing plusargs, file inputs, and library models. Those are real gaps for designs that use them. But the framing is wrong for the core corpus.

The reproducibility artifact is the VCD, not the simulation command. Testcase bundles are:
```
case_id/
  netlist.v          # frozen copy
  tb.v               # frozen copy of auto-generated testbench
  sim.vcd            # frozen output
  manifest.json      # frozen oracle
  build.json         # iverilog command, flags, library files used
```

`build.json` captures: simulator version, all `-D` defines, all `-l` library files, compilation flags. Re-running the tracer against the frozen VCD does not require re-simulation. Re-running the simulation for audit uses the frozen `build.json`. This is sufficient for the corpus's purpose: testing the tracer against known VCDs, not re-deriving VCDs.

The concession: designs that require external file inputs, plusargs, or proprietary library models cannot be reproduced from `build.json` alone and are rejected from the corpus.

---

**13. Rejecting >50-FF designs without reset guts Tier 2/3 coverage. CONCEDE — and reframe.**

The Round 2 fix was a retreat. The honest reframing is:

The automated pipeline covers ISCAS'85 (pure combinational), ISCAS'89 (sequential with reset), and ITC'99 (sequential with reset). These are Tier 1 and produce the bulk of the golden corpus.

Tier 2/3 (PicoRV32, Ibex, CVA6, Sky130) are in scope but require hand-authored testbenches. They are covered by the corpus through manual work, not automated generation. The plan's coverage matrix is updated to make this explicit: automated pipeline targets are ISCAS + ITC; Tier 2/3 are hand-authored contributions to `stress/` and `structural/`.

The claim "automated generation from large open-source netlists" is removed. The claim "the corpus includes large open-source netlists" stands, because hand-authored coverage still counts.

---

**14. Structural taxonomy still ambiguous after rename. CONCEDE.**

The `structural_class` field does not resolve what the tracer is expected to report for black-box cases. The semantics document from point 2 must define this explicitly.

For black-box cases: the expected answer is the signal at the boundary of the black box visible to the netlist (the input port of the black box that carries X). That is the last point the tracer can observe. This is stated explicitly in the semantics document and encoded as the `trace_endpoint` value. The `structural_class` field is retained only to describe *how* the X traversed a structural feature, as a secondary annotation for coverage analysis, not as a grading input.

---

**15. Timing schema is internally inconsistent. CONCEDE.**

All times are integers in simulator ticks. The `timescale` field in `sim_env` is the only place physical time appears. `clock_period_ns` is removed. The manifest schema uses `clock_period_ticks` everywhere. All absolute times (`injection.time`, `query.time`, `force_release_time`) are ticks. Conversion to nanoseconds uses `timescale` and is done only in human-readable display, never in the schema or in validation logic.

---

**16. Top-module assumption is unstable. CONCEDE.**

Fix:
- Testcase bundles include a `top_instance` field in `manifest.json` containing the elaborated instance name as seen by the simulator.
- For auto-generated testbenches: the wrapper instantiates the DUT as `dut` and all hierarchical paths in the manifest are rooted at `tb.dut`, not `top`.
- For hand-authored testbenches: the `top_instance` is specified by the author and validated against the elaborated hierarchy at submission time via `pyslang` elaboration.
- The examples throughout the plan that use `top.u_core.*` are illustrative shorthand only; the schema validator enforces that the actual manifest path matches the elaborated hierarchy.

---

## Summary of the Real Changes Required

The Round 3 critique reveals a pattern that the Round 2 concessions made worse: each accommodation loosened a constraint rather than removing the scenario that made the constraint hard to hold. The correct response to most of the causality critiques is restriction, not relaxation.

The revised plan rests on four structural decisions that were not in the original:

1. **Two injection methods only:** `$deposit` on RTL-level FFs; `force` on gate-level primary inputs. All other injection methods are manual only.
2. **No wrapper mode:** downloaded netlists with existing testbenches are either replaced with auto-generated testbenches or require hand-authored work.
3. **Automated pipeline targets Tier 1 only:** ISCAS + ITC. Tier 2/3 coverage is hand-authored.
4. **Semantics document precedes corpus:** `tracing_policy` is a normative spec, not a label. No testcase is generated without it.

The critique is right that the original plan's scope was overambitious relative to what automated generation can reliably produce. The fix is to be explicit about that boundary rather than paper over it with heuristics.
