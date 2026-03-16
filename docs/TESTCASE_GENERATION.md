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

