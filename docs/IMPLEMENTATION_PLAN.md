# X-Tracer for Verilog Gate-Level Netlists: Implementation Plan

## Goal

Build a high-performance X-tracer for Verilog gate-level netlists that takes:

1. A set of Verilog files
2. A value change dump (VCD) file
3. A full hierarchical signal path
4. A time value

Given a signal that is `X` at the specified time, the program should trace backward through both time and the input cone to identify the root cause of that unknown value.

## Core Architecture

The implementation should use a native C++ core with a thin CLI layer. The design should favor existing libraries and tools where they reduce parser and waveform risk without sacrificing runtime performance.

Recommended foundation:

- Netlist ingestion: Yosys frontend first
- Optional alternate frontend: Surelog/UHDM for more difficult source inputs
- Waveform handling: direct VCD support, with optional cached FST conversion for repeated analysis

## Revised Execution Plan

### 1. Build the testcase program first

Testcase generation and collection is the first project phase, not a late verification task. The testcase corpus defines expected behavior for root-cause analysis.

The initial corpus should cover:

- Pure combinational `X` propagation
- Reconvergent cones
- Mux/select ambiguity
- Flop/latch state corruption across time
- Reset/set/enable interactions
- Undriven nets and floating inputs
- Black-box or unknown library outputs
- Multiple simultaneous candidate causes
- Large synthetic stress cases for performance

### 2. Split testcase work into two tracks

- Hand-authored golden cases
  - Small designs
  - Exact expected answers
  - Human-reviewed root-cause outputs
- Generated cases
  - Parameterized templates or randomized generators
  - Variable cone depth, reconvergence, and sequential depth
  - Stress coverage for scale and corner cases

### 3. Define expected outputs before implementation

Each testcase should specify:

- Verilog files
- VCD file
- Query signal path
- Query time
- Expected root-cause class
- Expected trace endpoints or ranked candidate set
- Notes explaining correctness

### 4. Add a testcase generator harness

The harness should emit:

- Netlist source
- Stimulus or simulation driver
- VCD
- Manifest JSON for the query and expected answer
- Optional minimized explanation graph for debugging

### 5. Build the core implementation after the corpus exists

The implementation order should be:

1. Testcase corpus and generator
2. Netlist frontend and IR
3. Waveform ingestion/indexing
4. Trace semantics engine
5. Root-cause ranking/classification
6. Performance optimization
7. CLI/reporting

### 6. Promote correctness to an early-stage workstream

Correctness work starts immediately and runs in parallel with implementation. This workstream owns:

- Corpus design
- Golden expected answers
- Regression harness
- Coverage tracking by failure mode

## Internal Design Direction

### Netlist IR

Use a canonical bit-level internal representation with:

- Hierarchical signal ID
- Bit index
- Driver cell reference
- Fanin edges
- Fanout edges
- Sequential edges
- Source metadata

Serialize this IR to disk so downstream stages do not need to repeatedly parse Verilog.

### Waveform Storage

Map hierarchical waveform paths onto IR node IDs and store signal histories compactly:

- Timestamp deltas where possible
- Compact 4-state value encoding
- Fast lookup of value-at-time and previous-change-at-or-before-time

The first version can stream raw VCD into this store. A later optimization can cache an FST-backed or indexed representation for repeated runs on large dumps.

### Trace Engine

The tracing algorithm should be time-aware and structural:

- Start from `(signal, bit, time)`
- Confirm the value is `X`
- Move to the most recent causally relevant event
- Walk backward through combinational or sequential predecessors
- Apply cell-specific semantics to identify which inputs could explain the `X`

Examples:

- Combinational gates: follow ambiguity-causing or controlling inputs
- Muxes: follow selected input if select is known, branch if select is `X`
- Flops/latches: jump to prior capture conditions and trace `D`, reset/set, enable, and clock-related conditions

### Root-Cause Classification

The tool should classify the result, not only produce a raw cone. Initial root-cause categories should include:

- Upstream primary input was `X`
- Flop state already `X` at prior capture
- Unknown control produced ambiguity
- Undriven or unconnected net
- Black-box or library output unknown
- Unsupported cell semantics

### Performance Strategy

Performance requirements should be treated as first-class design constraints:

- Memoize repeated subproblems
- Merge duplicate structural/time states
- Prefer latest causally relevant predecessors
- Stop early on known terminal conditions
- Use compact IDs and interned names
- Use arena allocation where it improves locality and reduces overhead

## Agent Workstreams

- Agent 1: Testcase corpus and generator
- Agent 2: Netlist frontend and IR
- Agent 3: Waveform storage/indexing
- Agent 4: Trace semantics engine
- Agent 5: Correctness/regression infrastructure
- Agent 6: Performance/scalability
- Agent 7: CLI/reporting

## Milestones

### Phase 1

Build the testcase corpus, generator, and regression harness.

### Phase 2

Parse gate-level Verilog, build the bit-level graph, and resolve queried hierarchical signals.

### Phase 3

Ingest VCD and answer value-at-time queries accurately and efficiently.

### Phase 4

Implement backward time-aware tracing for core combinational cells, muxes, and flip-flops.

### Phase 5

Add root-cause classification, ranking, pruning, and memoization.

### Phase 6

Optimize for large netlists and waveform files, then harden the CLI and reporting flow.

## Immediate Next Step

Turn the testcase-first phase into a concrete design:

- Repository layout
- Testcase manifest schema
- Generator strategy
- First set of high-value golden and generated cases
