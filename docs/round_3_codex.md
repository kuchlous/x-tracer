# Round 3 — Codex

## Round 4 Critique

1. **The “sole causality holds by construction” claim is still false.**  
   Attacking: **Round 3 Defense, point 1**: “`force` on module primary inputs with no competing driver” and “The oracle is ‘injection is the sole cause’ and it holds because the two permitted methods cannot create secondary X sources by construction.”  
   Failure mode: forcing a primary input to `X` absolutely can create secondary X sources that are not semantically equivalent to “the input is the sole cause.” If that input feeds protocol logic, arbitration, reset sequencing, write enables, or address decode, the design can enter states where multiple internal effects independently generate X later. Your own earlier examples about control perturbation still apply because a primary input can itself be a control. “No competing driver” only means the port assignment is uncontested; it does not mean downstream behavior is causally simple.

2. **You quietly broke gate-level sequential coverage while still claiming ISCAS’89 and ITC’99 remain automated targets.**  
   Attacking: **Round 3 Defense, points 10 and 13**: “Gate-level netlists use primary-input injection only” and “The automated pipeline covers ISCAS’85, ISCAS’89, and ITC’99.”  
   Failure mode: ISCAS’89 and ITC’99 were originally justified as sequential benchmarks. If gate-level injection is now restricted to primary inputs only, you are no longer testing injected sequential state in those netlists. You have removed the very mechanism needed to create “FF-local unknown then propagate through captures” cases at gate level, but you still market those suites as sequential coverage. That is a bait-and-switch: primary-input X at a gate-level sequential design is not equivalent to direct state corruption coverage.

3. **The semantics document is now doing all the hard work, which means the testcase plan still has no operational semantics.**  
   Attacking: **Round 3 Defense, point 2**: “This document is a prerequisite deliverable. No testcases are generated until it exists.”  
   Failure mode: this is not a fix to the plan under review; it is an admission that the plan cannot currently define correctness. The plan still does not specify what the tracer must return, how many answers are allowed, or how answer comparison works. “Expected becomes a list” creates new ambiguity immediately:
   - Is order significant?
   - Must the tracer return all parents or any one?
   - Are equivalent paths deduplicated by signal or by event?
   - What if the list is huge in reconvergent logic?  
   You have replaced one undefined oracle with another and outsourced the missing semantics to a nonexistent future document.

4. **“Report all” is an unbounded oracle that will collapse on real reconvergence.**  
   Attacking: **Round 3 Defense, point 2**: “Multi-parent ranking: when multiple signals cause the same X, report all.”  
   Failure mode: in realistic gate-level cones, especially with reconvergent fanout and shared enables, “all causes” can explode combinatorially or depend on fine semantic choices about masking and equivalence. Your manifests are supposed to be stable golden answers, but now a tiny synthesis change or library mapping can change the count and identity of “all” parents without changing user-visible behavior. That makes the corpus hypersensitive to representation details rather than tracer correctness.

5. **The query-time convention is arbitrary and does not solve sequential ambiguity.**  
   Attacking: **Round 3 Defense, point 6**: “Queries are always placed at `N * clock_period_ticks + half_period_ticks` — between rising edges.”  
   Failure mode: sampling halfway between clock edges does nothing to resolve the hard cases you claim to care about:
   - Asynchronous resets and latches are not edge-bounded.
   - Combinational settling delays and delta-cycle behavior are simulator/model dependent even between edges.
   - In multi-phase or generated-clock designs, “half period” is meaningless even if you exclude multi-clock automation, because derived enables and level-sensitive paths still exist in supposedly single-clock designs.
   - If `force` is held for the full run on a primary input, every between-edge sample is contaminated by a permanent source, which sidesteps rather than tests temporal tracing semantics.

6. **The auto-generated testbench is still under-specified where it matters most: stimulus realism.**  
   Attacking: **Round 3 Defense, points 5, 7, and 12**: “discard original and auto-generate,” “reset polarity must be specified,” and “the reproducibility artifact is the VCD.”  
   Failure mode: replacing real testbenches with simplistic auto-generated ones guts meaningful behavior. Driving all non-reset inputs to constant known values creates trivialized operating modes:
   - datapaths stuck in idle
   - state machines never leaving reset/boot states
   - outputs never toggling except through artificial injection
   - dead code and dormant cones never exercised  
   The resulting cases are structurally valid but behaviorally sterile. You are generating tracer tests against degenerate simulations, not representative design execution.

7. **“Reset polarity metadata” is nowhere near enough reset metadata.**  
   Attacking: **Round 3 Defense, point 7**: “reset polarity must be specified as a metadata field.”  
   Failure mode: polarity is the smallest part of reset behavior. You still do not specify:
   - synchronous vs asynchronous reset
   - required assertion length
   - clock-domain sequencing
   - whether some blocks require enables/configuration after reset
   - whether reset must be accompanied by valid clock toggling before deassertion  
   A one-bit metadata flag cannot make auto-generated initialization credible for real sequential netlists.

8. **You removed wrapper mode, which destroys most of the “open-source netlist” value proposition.**  
   Attacking: **Round 3 Defense, point 5**: “Case 2: Testbench Exists mode is eliminated.”  
   Failure mode: many downloaded designs only become meaningful through their provided bench, memory init flow, or harness. By discarding that and insisting on simplistic bench generation or manual authoring, your plan no longer scales to the sources it advertised. This is not just reduced convenience; it eliminates the claimed leverage from existing open-source ecosystems and leaves you with hand-maintained bespoke benches for anything nontrivial.

9. **The target-selection algorithm is still semantically detached from testcase value.**  
   Attacking: **Round 3 Defense, point 11**: the five structural categories including “highest-fanout,” “lowest-fanout,” and “randomly sampled net from the backward cone of the highest-fanout target.”  
   Failure mode: these categories are graph-theoretic, not semantic. They do not target the difficult behaviors the Motivation claimed mattered: sequential capture timing, control-vs-data provenance, reconvergence semantics, and masking. “Highest fanout” is often just reset distribution, clock-gate enable trees, or bus broadcast glue. “Lowest fanout > 1” is meaningless as a difficulty criterion. Random sampling from a cone is coverage theater, not testcase design.

10. **You still have an unresolved contradiction between “primary-input force held for duration” and clean causal endpoints.**  
    Attacking: **Round 3 Defense, point 9**: “The only remaining `force` use is on primary inputs, which are held X for the duration of the simulation.”  
    Failure mode: a permanently forced input means the source never resolves, so every observed X later may be attributable either to the persistent input or to downstream captured/derived states. If your semantics document says stop at the first sequential capture boundary, then the manifest must prefer downstream capture events over the still-active forced source for some queries. If it does not, you are again hardcoding a source policy that conflicts with sequential endpoint semantics. The plan has not reconciled persistent injection with time-local root-cause answers.

11. **The “reproducibility artifact is the VCD” move guts the purpose of the corpus as an implementation oracle.**  
    Attacking: **Round 3 Defense, point 12**: “Re-running the tracer against the frozen VCD does not require re-simulation.”  
    Failure mode: if the corpus is only a set of frozen VCDs plus manifests, then the whole elaborate generation pipeline becomes non-auditable unless someone can reproduce those VCDs. You concede that designs with external files, plusargs, or library models are rejected, but even accepted designs remain brittle:
    - VCD completeness depends on dump scope choices
    - signal naming stability depends on elaboration
    - library model behavior depends on compile set  
    A frozen waveform is not a substitute for a reproducible testcase definition when the oracle is supposed to validate tracer semantics, not just replay one artifact forever.

12. **Your top-instance/path stabilization story still ignores synthesis and elaboration instability across corpus updates.**  
    Attacking: **Round 3 Defense, point 16**: “all hierarchical paths in the manifest are rooted at `tb.dut`” and “validated against the elaborated hierarchy.”  
    Failure mode: validation only proves the path exists in that one elaboration. It does not make the path stable across:
    - regenerated RTL netlists
    - different synthesis versions
    - generate-block renumbering
    - flattened vs hierarchical builds
    - library wrapper differences  
    Since your oracle is path-based, small tooling drift can invalidate manifests without changing the logical testcase. You have no canonical signal identity beyond fragile hierarchical names.

13. **The plan now depends on manual work exactly where the hard bugs live, which undermines the automation claim.**  
    Attacking: **Round 3 Defense, points 1, 5, 8, and 13**: internal/control injections manual only, preserved benches manual only, multi-clock manual only, Tier 2/3 manual only.  
    Failure mode: everything difficult has been pushed out of the automated pipeline:
    - control X
    - internal net corruption
    - existing complex benches
    - multi-clock designs
    - large realistic cores  
    What remains automated is the easy slice. The original plan sold automation as the path to broad, realistic coverage; the revised plan automates toy and mid-tier cases while hand-waving the rest as future manual effort. That is a scope collapse, not a repaired strategy.

14. **The black-box handling is still semantically dubious.**  
    Attacking: **Round 3 Defense, point 14**: “For black-box cases: the expected answer is the signal at the boundary of the black box visible to the netlist.”  
    Failure mode: this confuses observability boundary with causality. If the X entered a black box and emerged later, the “input port of the black box that carries X” may not be the correct backward endpoint under a policy that stops at sequential capture boundaries or reports all causes. If multiple black-box inputs are X, or the output is unknown because the model is opaque rather than because a specific visible input is X, your chosen endpoint is arbitrary. You are still inventing semantics case-by-case instead of deriving them from one coherent rule set.

15. **You keep claiming restriction fixes causality, but restriction also removes categories the corpus structure still advertises.**  
    Attacking: original corpus structure and latest defense together: `structural/undriven_net`, `black_box`, `multi_driver`, plus **Round 3 Defense, point 1** removing internal/control injection from automation.  
    Failure mode: with only primary-input `force` at gate level and RTL FF `$deposit`, automated generation no longer has a credible way to create many of the structural categories in the listed corpus. `multi_driver` especially is not something you can meaningfully exercise by forcing an uncontested primary input unless the design already contains the contested condition, in which case your “sole causality” story breaks again. The directory taxonomy still overpromises behaviors your revised generation rules cannot produce.

16. **The revised plan still lacks an acceptance rule for when a testcase is “golden.”**  
    Attacking: latest defense overall, especially **points 2, 12, and 15**.  
    Failure mode: you have changed answer shape, timing basis, path roots, and generation scope, but you still never define the concrete grading rule:
    - exact set equality between tracer output and `expected`?
    - allow supersets?
    - allow equivalent endpoints across hierarchy boundaries?
    - how are times compared if multiple candidate events are simultaneous within a tick?
    - what constitutes a mismatch versus acceptable nondeterminism?  
    Without that, “golden” remains a label, not a test oracle.

The pattern is worse now: each revision narrows scope, but the remaining scope is still not specified tightly enough to produce stable, unique, mechanically checkable answers. The plan is no longer overambitious; it is underdefined.
