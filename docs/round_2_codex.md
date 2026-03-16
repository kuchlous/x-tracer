# Round 2 — Codex

## Round 3 Critique

1. **You destroyed the oracle and still call this a pass/fail corpus.**  
   Attacking: latest defense, **“manifests do not assert ‘injection is the sole cause.’ They assert ‘injection is a known cause’”** and **“A tracer that reports the injection target passes. A tracer that reports a race-caused secondary X may also be correct.”**  
   Failure mode: this is no longer a testcase with a unique expected answer. It is an admission that multiple incompatible answers may be accepted. That makes automated grading undefined unless you enumerate the full allowed-answer set per testcase, which you do not. A tracer that always reports the original injection point could pass. A tracer that always reports a downstream race could also pass. That is not “ground truth”; it is surrender.

2. **`tracing_policy` is a label, not a semantics definition.**  
   Attacking: latest defense, **“add a required `tracing_policy` field ... e.g. `stop_at_sequential_capture_boundary_v1`.”**  
   Failure mode: a version string does not define behavior. You still have not specified:
   - whether the trace stops at the first sequential element encountered backward from the query or the first capture event in time
   - whether a mux select that causes X masks data-path provenance
   - how multiple simultaneous parents are ranked
   - whether the answer is a signal, an event, or a `(signal, time)` pair  
   Without a normative semantics document, `tracing_policy` is just a decorative tag attached to ambiguous manifests.

3. **Layer 6 does not establish causality; it only proves a weak counterfactual that misses interaction bugs.**  
   Attacking: latest defense, **“run the same simulation without the injection and verify the query signal is not X at query time.”**  
   Failure mode: this still accepts contaminated cases where the query becomes X only because the injection perturbs the design enough to trigger a second independent fault. Example:
   - `force` a control net to X for one cycle
   - that changes arbitration
   - two writers now drive a bus in the next cycle
   - query becomes X due to the multi-driver conflict, not the original injection cone  
   The no-injection run stays clean, so Layer 6 passes. Your testcase still has no unique causal story.

4. **Your “outside the forward cone” contamination heuristic is invalid on exactly the semantics you claim to care about.**  
   Attacking: latest defense, **“scan the VCD for any signal becoming X that is not in the forward cone of the injection target.”**  
   Failure modes:
   - Static netlist forward cones do not capture X introduced through control dependence in `if`/`case` lowering.
   - Synthesized muxes may be decomposed into gates; an X on select can contaminate both data branches in simulation even when the structural “cone” analysis says otherwise.
   - Bidirectional nets, tri-state primitives, `tranif*`, and library UDPs break simple cone assumptions entirely.
   - Multi-driver resolution creates X on nets whose graph ancestry is not a plain forward cone from one source.  
   You are trying to detect dynamic semantic contamination with a static topology filter. That will both miss real contamination and flag legal propagation as “outside cone.”

5. **The wrapper strategy is still technically impossible under your own “never modify original testbench” rule.**  
   Attacking: original plan, **“Never modify the original testbench. Compile a wrapper alongside it”**, and latest defense, **“force `$dumpvars(0, top)` by the wrapper, overriding any existing testbench dump scope.”**  
   Failure modes:
   - A wrapper cannot reliably “override” an existing `$dumpfile`, `$dumpvars`, `$dumpoff`, or early `$finish` in another testbench module.
   - If the original testbench names the DUT something other than `top`, your forced dump scope is wrong.
   - If the original testbench instantiates multiple DUTs or uses generate-time top selection, your wrapper has no authoritative scope.
   - If the original testbench terminates before your injection time, compiling another `initial` block does not rescue the run.  
   “Compile a wrapper” is not a control plane. You do not own the existing bench’s scheduling or dump configuration.

6. **Your `query_nba` field is fake precision.**  
   Attacking: latest defense, **“`query_nba: false` means the query value is read from the VCD as it appears (post-NBA by VCD convention).”**  
   Failure mode: VCD does not give you a principled per-query pre-NBA/post-NBA semantic switch. It records value changes by simulation time and dump behavior; it does not preserve a clean oracle of “this sample is pre-NBA” vs “post-NBA” for arbitrary signals and simulators. You are inventing an unobservable manifest field and pretending it resolves timing ambiguity.

7. **The reset-polarity retry heuristic will misclassify valid designs as “working” or “clean.”**  
   Attacking: latest defense, **“after the initial reset pulse, check whether FF outputs ... become non-X. If they remain X, invert polarity and retry once.”**  
   Failure modes:
   - Many real designs deliberately leave some flops unreset; “non-X after reset” is not a valid reset-detection criterion.
   - Both polarities can yield non-X values if inputs are driven and logic settles combinationally, even though one polarity never actually exercised reset.
   - A design held permanently in reset can still look “clean” because reset values are known.
   - Async resets with minimum pulse widths or clock-domain sequencing will not be handled by a one-shot polarity inversion.  
   You are conflating “known values exist” with “reset was correctly applied.” They are not the same thing.

8. **Multi-clock support is still hand-waving, not a workable plan.**  
   Attacking: latest defense, **“detect all clock candidates, instantiate separate `always` blocks for each, log a warning ... multi-clock tests are less reliable.”**  
   Failure mode: “less reliable” is not an acceptance rule. Your manifests still encode single absolute times like `query.time` and `injection.time` without specifying:
   - which clock domain defines capture semantics
   - whether the query is before or after a destination-domain synchronizer edge
   - how asynchronous crossings are traced  
   In a two-clock design, `time=150` is meaningless as a tracing oracle without domain-aware semantics. A warning in the manifest does not fix that.

9. **Your `force`/`release` repair adds new ambiguity and still does not model real behavior.**  
   Attacking: latest defense, **“`force` must always be paired with a `release` after a fixed number of cycles (default: 1 clock period).”**  
   Failure modes:
   - One cycle is arbitrary. Too short and the X never crosses a pipeline boundary. Too long and you create persistent contamination.
   - Which clock period applies on a multi-clock or clock-gated target?
   - A control-net force released after one cycle can create metastable-looking downstream behavior over many cycles that your manifest still attributes to a single source.
   - Release timing relative to active edges is not specified, so two simulators or two testbenches can observe different behavior from the same manifest.  
   You replaced one uncontrolled semantic distortion with another.

10. **The “deposit only on FF state elements” rule is not operationally defined for actual gate netlists.**  
    Attacking: latest defense, **“`$deposit` is only valid for FF state elements (the state register itself, not the output net). The scanner must verify the target has no continuous driver.”**  
    Failure modes:
    - In many gate netlists there is no clean distinction between “state register itself” and “output net” available as a writable hierarchical object.
    - Standard-cell flops expose pins and internal regs through library models, not through a canonical state variable you can deposit onto.
    - “No continuous driver” is not enough to identify a legal storage target; plenty of non-storage nets also lack continuous drivers.
    - Black-boxed or encrypted library models may not expose anything writable at all.  
    This is not a scanner rule; it is a simulator- and library-model-specific assumption with no generic implementation path.

11. **Your control-signal classification is still fantasy on synthesized netlists.**  
    Attacking: latest defense, **“identify control signals structurally”** using `get_port_function(...)= 'select'/'enable'`.  
    Failure modes:
    - Yosys/DC often lower muxes into boolean gates; there is no surviving “select port” to inspect.
    - Clock enables are commonly compiled into feedback muxes or integrated-library cells with vendor-specific pin names.
    - Arithmetic datapaths often encode control influence through one-hot gating, not named select pins.
    - The plan spans ISCAS, ITC, Sky130, PicoRV32, Ibex, CVA6, EPFL. There is no single port-function taxonomy that covers that mix.  
    You are promising role-aware sampling based on metadata the netlists will often not contain.

12. **Your reproducibility patch is still missing the actual inputs that determine behavior.**  
    Attacking: latest defense, added manifest fields `sim_env`, `timing`, `x_injection`.  
    Failure modes:
    - No record of the actual stimulus trace applied to primary inputs over time.
    - No capture of plusargs, file inputs, memory initialization files, or environment variables used by an existing testbench.
    - No record of the wrapper source or generated testbench version/hash.
    - No record of library models compiled alongside the DUT.  
    “Simulator version” and “timescale” are not enough. Two runs with the same manifest can still produce different VCDs because the real behavioral inputs are undocumented.

13. **The “reject designs without reset and >50 sequential elements” change quietly guts your source strategy.**  
    Attacking: latest defense, **“Designs without a reset port and with more than N sequential elements (threshold: 50) are rejected”**, plus original sections **“Tier 2/3”** and the coverage matrix using CVA6, PicoRV32, Ibex, tapeout netlists.  
    Failure mode: this is not a fix; it is a retreat from the hard cases the plan was supposed to cover. Large open-source netlists are exactly where reset trees, partial reset, SRAM macros, scan logic, and multi-clock behavior show up. Your workaround will either reject them outright or reduce coverage to toy subsets, making the “real-design coverage” claim false.

14. **The structural taxonomy is still semantically incoherent after your rename.**  
    Attacking: latest defense, **“`structural_class` ... used only when the injection exploits a structural condition.”**  
    Failure mode: you still have not said whether the tracer is expected to report:
    - the injected source,
    - the structural feature that allowed propagation,
    - both,
    - or one depending on `tracing_policy`.  
    Example: if you `force` a net feeding a black box output, is the expected answer the forced net, the black box boundary, or both? Renaming `root_cause_class` to `injection_class` just moved the ambiguity into a new field.

15. **Your timing schema is internally inconsistent.**  
    Attacking: latest defense manifest snippet, **`"timescale": "1ns/1ps"`** and **`"clock_period_ns": 10`** alongside raw times like `"time": 150`.  
    Failure mode: half the schema uses simulator timescale strings, half hardcodes nanoseconds, and the original manifest uses unitless integers. That is exactly how you get off-by-1000 bugs when a testcase moves from `1ns/1ps` to `10ps/1ps`. Either every time is an integer in simulator ticks tied to the declared timescale, or every time is a unit-annotated physical value. Right now it is both.

16. **The top-module assumptions remain scattered and wrong.**  
    Attacking: original examples throughout: **`top.u_core...`**, **`$dumpvars(0, top)`**, wrapper/injection examples using `top.*`, and auto-generated TB instantiating `top_module dut`.  
    Failure mode: the plan never defines how the real elaborated top is discovered and normalized across:
    - downloaded benches with their own top-level harness
    - synthesized RTL with renamed or flattened tops
    - multiple candidate tops in a repo
    - generated instance names that differ between synthesis runs  
    This matters because your manifest stores hierarchical paths as the oracle. If the path naming is unstable, the testcase is unstable.

The unresolved pattern is the same across all of this: each “fix” weakens the claim, narrows the scope, or adds metadata labels, but the plan still does not produce a stable, unique, simulator-independent oracle for the behavior it says it will test.
