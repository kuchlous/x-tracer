# Round 4 — Codex

1. **Point 16, “A testcase is promoted to `golden` iff … the tracer under test is run against the VCD.”**  
   This is circular and directly contradicts the original claim that testcases come first. A testcase corpus is supposed to be an oracle for the tracer; here, goldenness depends on whether some tracer passes it. Concrete failure mode: two different tracer implementations produce different outputs on the same case; one passes the weak cone-membership check, the other fails. Is the testcase golden or not? Your answer now depends on the implementation under evaluation, which destroys the notion of an implementation-independent corpus.

2. **Point 3, “A testcase passes iff the tracer’s output set contains at least one element `(S, T)` …” and Point 16, “Superset is acceptable.”**  
   This oracle is so weak that a useless tracer can pass. Concrete failure mode: implement a tracer that returns every signal/time pair in the design that ever carried X between `injection_time` and `query_time`. Since `tracer_output ∩ cone_members ≠ ∅` will almost always hold, it passes nearly everything. You are no longer testing whether the tracer finds the right cause; you are testing whether it can dump a large enough over-approximation.

3. **Point 3, the oracle definition itself is internally confused: “`S` is in the static backward cone of the query signal” and “`S` is an ancestor-or-equal of the injection target in the static forward cone from the injection point.”**  
   The terminology is muddled enough to be non-operational. “Ancestor” normally means upstream; “forward cone from the injection point” means downstream. Concrete failure mode: different engineers will implement different set constructions for `cone_members`, especially around whether equality with query/injection is allowed and whether sequential boundaries are traversed through `Q->D` edges, and your pass/fail result will change based on that interpretation rather than tracer behavior.

4. **Point 3 and Point 16, static `cone_members` as the grading oracle.**  
   Static path membership ignores sensitization, masking, and time alignment, which were the entire reason this problem was hard in the first place. Concrete failure mode: a node lies on some topological path from injection to query and briefly becomes X at `t=20`, but by `t=150` the query’s actual X comes through a different sequential capture path. A tracer that reports the irrelevant early node still passes because it is in `cone_members` and had X sometime in the broad window. That is not tracing correctness; that is graph reachability.

5. **Point 16, “Times are checked as `injection_time ≤ T ≤ query_time`.”**  
   This timing rule is grossly insufficient. It allows reporting a node that was X at any irrelevant time in the interval, even if it had already resolved long before the query’s causal event. Concrete failure mode: deposit X into a register at `t=0`, it resolves at `t=10`, the query becomes X at `t=150` because a later captured descendant stayed X. A tracer that always reports the injected register at `t=0` passes even if the intended semantics are about the closest explanatory event to the observation time.

6. **Point 6, “Behaviorally sterile simulations are acceptable … The tracer either finds a valid ancestor or it doesn’t.”**  
   This concedes away the hard semantics while still pretending to test them. Constant-zero stimulus will routinely avoid the control interactions, reconvergence activation, and sequential enable behavior that make tracing difficult. Concrete failure mode: a mux select is held constant so one data branch is never active; your static cone still contains both branches, but the waveform only exercises one trivial path. The testcase then says nothing about whether the tracer handles data/control disambiguation under realistic toggling.

7. **Point 9, the revised selection strategy: “Deepest node,” “reconvergent point,” “module port boundary crossing,” etc.**  
   This still does not line up with your actual automated scope. In Point 15 you collapse automation to `combinational/` on ISCAS’85, yet Point 9 still talks about “deep sequential traversal” and RTL-only FF outputs. Concrete failure mode: the selection algorithm advertises coverage dimensions that cannot exist in the only automated corpus you now allow. This is leftover scope inflation masquerading as a method.

8. **Point 15, “`sequential/` and `structural/` are hand-authored,” combined with Point 16’s golden rule.**  
   You never define how manual cases avoid the same oracle collapse. If they also use cone-membership, they are weak and permissive. If they use a stricter endpoint oracle, then the corpus has two incompatible notions of correctness. Concrete failure mode: the same tracer output can pass an automated combinational case under the weak oracle and fail a manual sequential case under a stronger one, with no unifying semantics document to explain why.

9. **Point 11, “A reviewer can re-run the simulation and get a bit-identical VCD.”**  
   This is asserted, not established. Even within a deterministic bench, VCD identity can depend on elaboration order, dump scope ordering, library model implementation details, and simulator version. You store a simulator version in `build.json`, but the claim is stronger: “bit-identical.” Concrete failure mode: two valid builds of the same files with different file ordering or tool minor versions produce the same logical behavior but different signal identifier allocation or dump ordering, so your audit criterion fails even though the testcase is semantically unchanged.

10. **Point 12, freezing netlists by checksum as the answer to path instability.**  
    This avoids one problem by making the corpus brittle and non-maintainable. Concrete failure mode: you fix a harmless syntax issue, rename an instance, or rerun synthesis with equivalent logic; every manifest path and checksum becomes “new testcase” territory. That means corpus evolution measures toolchain churn, not semantic coverage. You have replaced unstable signal identity with permanent testcase duplication.

11. **Point 14, black-box handling: “reporting any X-carrying black-box input … is a valid answer.”**  
    This completely guts black-box-specific validation. A tracer that knows nothing about black boxes and simply stops at the first visible upstream net will pass. Concrete failure mode: if multiple black-box inputs are X, or the output is unknown because the model is opaque rather than because one visible input is X, your oracle still accepts any visible input on some path. That does not test black-box reasoning; it exempts it.

12. **Point 16, “Cone non-triviality: `|cone_members| ≥ 2`.”**  
    This is a fake quality gate. A two-node “cone” can be injection target -> one wire/buffer -> query, which still exercises nothing interesting. Concrete failure mode: a testcase with exactly one intermediate assignment node passes the non-triviality filter and becomes `golden`, even though it provides no evidence about reconvergence, masking, sequential capture, or module-boundary behavior.

13. **Point 2 and Point 13 together create a scope contradiction you never resolved.**  
    Point 2 says automated gate-level targets are only ISCAS’85. Point 13 says automation targets “combinational and simple sequential cases.” Those statements are incompatible unless you define what “simple sequential” now means and where it comes from. Concrete failure mode: teams build tooling assuming some automated sequential stream exists, but your only explicit automated benchmark family is combinational. The plan still cannot state its actual deliverables cleanly.

14. **Point 8, “The original testbench is irrelevant … the structure is what matters.”**  
    That is an unsupported leap from structural reachability to tracer correctness. If the tracer semantics include anything temporal or state-related, the operating regime absolutely matters. Concrete failure mode: a signal is structurally on the path but only semantically relevant when a handshake is active or an enable opens a latch; your auto-generated constant stimulus never exercises that regime, yet the testcase still claims to cover the structure. You are confusing possible paths with exercised causes.

15. **Point 3’s `cone_members` manifest example is itself under-specified.**  
    You show a flat list of signal names, but do not define whether this set includes the query, includes repeated time-separated visits of the same signal, crosses sequential elements as separate events, or handles bit-select granularity. Concrete failure mode: a tracer returns `foo[3]` while `cone_members` stores `foo`; or it returns `foo` at two different capture times and only one is semantically relevant. Your oracle reduces these distinctions away, so different classes of mistakes become invisible.

16. **The central move in Points 3 and 16 does not “resolve” earlier critiques; it evades them by lowering the bar until almost any cone-adjacent answer counts.**  
    Concrete failure mode: a tracer that simply walks backward until it finds any X-bearing node on any legal path, without distinguishing control from data, earliest from latest, or capture from combinational propagation, now passes. That means the suite cannot detect exactly the subtle semantic bugs the original Motivation claimed were easy to miss.

The latest defense no longer describes a testcase generation plan with a sound oracle. It describes a reachability-based permissive filter that can certify badly over-approximate tracers, depends circularly on the tracer to bless cases as `golden`, and keeps shrinking scope without ever defining a stable correctness target.
