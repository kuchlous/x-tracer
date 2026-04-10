# Building X-Tracer: A War Story

## The Problem

Gate-level simulation (GLS) on real SoCs produces X values -- unknown logic states that propagate through millions of gates, cause test hangs, and make engineers miserable. The X shows up on some output bus 50,000 cycles into simulation. Where did it come from? Which flip-flop was uninitialized? Which reset was never driven? Which clock gate let an X through?

That is the question x-tracer was built to answer: given a signal that is X at time T in a VCD waveform, trace backward through a gate-level netlist to find the root cause.

The target was not a toy. It was a real 22nm ARM Cortex-A55 SoC -- 3.3 million gates, 480MB flat netlist, multi-gigabyte VCD files from Cadence Xcelium simulations with `-xprop F` (full X propagation mode).

---

## Phase 1: Synthetic Circuits and the First Tracer

Development began with what any sane person would do: small synthetic circuits. AND chains, MUX trees, flip-flop pipelines, reconvergent fanin networks. The kind of thing you can hold in your head and verify by inspection.

The first tracer was a recursive backward walk. Start at the X-valued signal. Find its driver gate. Check each input in the VCD. If an input is X, recurse into it. If no driver exists, it is a primary input -- root cause found. If it is a flip-flop, find the last clock edge, check D at that edge, and recurse. Simple enough.

A per-path visited set prevented infinite loops on combinational feedback. 384 synthetic test cases were generated using Icarus Verilog (`iverilog`), covering every gate type, bus width, and X injection pattern. The test infrastructure used three parallel agent swarms (S1, S2, S3) to generate cases across different complexity tiers -- single gates, multi-stage pipelines, and bus-level operations.

Everything worked. The tracer found root causes in every synthetic circuit. Then it met reality.

---

## Phase 2: The Netlist Parsing Problem

The first attempt to parse the real SoC netlist used `pyslang`, the Python bindings for the Slang SystemVerilog compiler. Pyslang understands full SystemVerilog semantics -- modules, generates, parameters, the works. It built a complete AST.

It also took 11 minutes to parse a 480MB netlist.

For a tool meant to be used interactively during debug sessions, 11 minutes of startup time is a non-starter. The netlist is flat post-place-and-route Verilog from Cadence Innovus. No generates. No parameters. No behavioral code. Just millions of lines of:

```verilog
NAND2_X1M_A9PP140ZTH_C30 inst_name (.A(net1), .B(net2), .ZN(net3));
```

A regex-based line-by-line parser was built instead (`fast_parser.py`). It reads the file without loading it entirely into memory, extracts module definitions and instantiations with compiled regular expressions, and infers port directions from naming conventions (Y, Z, ZN, Q are outputs; VDD, VSS are power/ground). Performance target: 480MB with 3.2 million instances in under 60 seconds. Actual performance: around 5 minutes -- not instant, but workable.

---

## Phase 3: Standard Cell Names Are Not What You Think

Real 22nm standard cell names look like this:

```
NAND2_X1M_A9PP140ZTH_C30
```

The structure is `FUNCTION_XDRIVE_TECHSUFFIX`. To determine a cell's logical function, you strip the drive strength suffix and the technology trailer. A NAND2 is a NAND2 regardless of whether it is X1M or X2B or X4A.

The initial regex for stripping drive strength matched `_X\d+[BM]_`. This worked for the cells that showed up in early testing. Then a blind validator agent -- a separate Claude instance running automated checks against the full cell library -- discovered that the cells also use drive suffixes like `_X1A_`, `_X2BB_`, and `_X3XB_`. The regex was only matching `[BM]` when it needed `[A-Z]` (or more precisely, one or more uppercase letters after the digit).

Commit `bf6347f` fixed this: "Fix drive strength regex: accept A/B/M/etc suffixes (validator-found bug)." A one-character regex change that would have silently caused every cell with an `A` or `XB` suffix to be treated as an unknown cell type, falling back to conservative all-inputs-are-causal tracing instead of precise backward cause analysis.

Additional cell support was needed for `PREICG` (pre-integrated clock gating) cells, and for stripping inverted-input suffixes appended to cell names.

---

## Phase 4: VCD at Scale -- Three Attempts

### Attempt 1: pywellen

The first VCD backend used `pywellen`, Python bindings for the Rust-based `wellen` VCD/FST parser. Fast, memory-efficient, battle-tested on open-source VCDs.

It panicked on the first real Xcelium VCD.

The problem: Cadence Xcelium writes VCD `Event` type entries (used for Verilog `event` variables). The wellen Rust parser had no handler for this type and crashed with an unrecoverable panic. The fix was to fork pywellen as `xtracer_vcd`, adding a conversion that maps Event entries to None values. Commit `7fb235a`: "Integrate xtracer_vcd: our fork of pywellen with Event type fix."

### Attempt 2: Python Line Parser

For cone-based loading (parsing only the signals in the backward cone of the query signal, not the entire 28-million-signal VCD), a Python line-by-line VCD parser was used. This worked but was painfully slow for multi-GB files: over 2 minutes for a 5GB VCD. A Python binary extraction script was tried next -- still too slow.

### Attempt 3: Rust Streaming Extractor

The solution was a custom Rust streaming VCD extractor built on the wellen API. It reads the VCD file once, extracts only the signals in the query cone, and streams results back. Performance: 50 seconds for 5.5GB. Commit `bc1a64c`: "Rust streaming VCD parser: 50s for 5.5GB (was 2+ min Python)."

### The Bus Lag Problem

Even with correct VCD parsing, values were wrong. A DFF's Q output would change from 0 to X at time 1000, but the bus wire it drove (say `data_bus[3]`) would still show 0 at time 1000 in the VCD. The bus-level value lagged behind the per-bit DFF output.

This is a Cadence Xcelium behavior: in `-xprop F` mode, per-instance port signals (like `gate.Q`) are updated at the simulation delta where the change occurs, but bus-level wire dumps may reflect an earlier delta's value.

The solution was to always prefer per-instance port signals when querying the VCD. Instead of looking up `data_bus[3]`, look up `tb.dut.ff_inst.Q`. The `_vcd_get_bit` function in `core.py` implements this as a candidate list: try the per-instance port signal first, then its escaped-identifier variant, then fall back to the bus wire.

---

## Phase 5: The LFSR Stress Test -- Three Days of Pain

The synthetic tests were too easy. Real circuits have feedback. To stress-test the tracer, a circuit was built with four stages of 2-to-1 LFSRs feeding into an 8-bit LFSR with XOR feedback. Every output feeds back to an input. The topology is a nightmare of reconvergent fanin and same-timestamp feedback.

### Problem 1: Exponential Blowup

The first run on the LFSR circuit produced 8,007 leaf nodes at depth 80 before hitting the recursion limit.

The per-path visited set was the culprit. It prevented revisiting a node on the *current* path (avoiding infinite loops), but when the DFS backtracked, the node was removed from the visited set, allowing sibling branches to re-explore the entire sub-tree. In a reconvergent circuit, this means every path through the fanin cone is explored independently -- exponential in the depth.

The fix was a three-color DFS, borrowed from the textbook algorithm for detecting cycles in directed graphs:

- **White**: unvisited
- **Gray** (`exploring` set): currently on the DFS stack -- reaching a gray node means we found a cycle
- **Black** (`memo` dict): fully explored -- reaching a black node means we can reuse the cached result

The `exploring` set is global (shared across all recursive calls), not per-path. A node goes gray when we start exploring it and black when all its children are fully explored. This prevents sibling re-exploration entirely.

Signal-level memoization (`sig_memo`) was added on top: if we have already traced `signal[bit]` at any time and the result was purely combinational (not a sequential capture), we can reuse the result at a different time. This handles the common case of reconvergent combinational cones.

### Problem 2: Same-Timestamp Feedback Loops

With the blowup fixed, the tracer entered infinite loops instead.

The problem: in VCD dumps, a clock edge at time T causes all DFFs to update their Q outputs at time T. The combinational logic driven by those Q outputs also settles at time T. So the D input of a downstream DFF shows its new value at time T -- but in real hardware, that DFF captured D from *before* the clock edge.

In an LFSR with feedback, DFF_A.Q feeds through XOR gates to DFF_B.D, and DFF_B.Q feeds back through XOR gates to DFF_A.D. At time T (the clock edge), VCD shows:
- DFF_A.Q = X (just changed)
- DFF_B.D = X (combinational from DFF_A.Q)
- DFF_B.Q = X (just changed)
- DFF_A.D = X (combinational from DFF_B.Q)

The tracer sees DFF_A.Q is X, looks at D at the clock edge, sees X, recurses into the combinational cone, reaches DFF_B.Q, looks at its D at the clock edge, sees X, recurses, reaches DFF_A.Q -- cycle.

Three brainstorm agents were launched in parallel to solve this. Two of the three converged on the same solution: **pre-edge D sampling**. When the clock edge time equals the query time, sample D at `T-1` instead of `T`. At `T-1`, D holds its *pre-edge* value -- the value the DFF actually captured. This breaks the feedback loop because at `T-1`, the upstream DFF's Q has not yet changed.

From `core.py`, lines 322-329:
```python
# When the clock edge is at the same time as our query, VCD shows D's
# post-edge value (combinational outputs update at the same timestamp).
# In real hardware, the DFF captures D from BEFORE the edge.  Sample D
# at edge_time-1 to get the pre-edge value and trace from there.
if edge_time == time:
    d_sample_time = edge_time - 1
else:
    d_sample_time = edge_time
```

### Problem 3: Hierarchy Mismatch

Even with the algorithm fixed, the LFSR test failed because signals in the VCD used `tb.dut.*` paths while the netlist used `stress_net.*` paths. The solution was to parse both the testbench (`tb.v`) and the netlist with `top_module='tb'`, so the netlist graph includes the testbench hierarchy wrapper.

### Result

After all three fixes, the LFSR stress test traced to completion in 5 milliseconds: 3,010 leaves, all with `cause_type="primary_input"` pointing to `inject_data[0]`. Commit `97e8ae0`: "Three-color DFS, pre-edge D sampling, per-instance VCD ports: LFSR stress test traces to inject_data."

---

## Phase 6: Edge Case Designs and Temporal Backtrack

Five targeted edge case designs were built to probe specific weaknesses:

1. **deep_pipeline** -- 104-stage flip-flop pipeline
2. **wide_fanout** -- single source fanning out to many sinks
3. **clock_crossing** -- signals crossing between clock domains
4. **tristate_bus** -- buses with tri-state drivers
5. **nested_clock_gate** -- cascaded PREICG clock gating cells

### The Xcelium License Detour

Initial VCDs for these tests were generated synthetically in Python -- writing VCD files directly with known X injection patterns. This worked for basic validation but produced inaccurate X propagation compared to real simulation.

When it came time to run real Xcelium simulations, the license server was down. Hours were lost. The eventual fix: `CDS_LIC_FILE` needed a second license server added (`192.168.5.8`). A reminder that infrastructure problems can block progress just as effectively as algorithmic ones.

With real Xcelium VCDs (commit `04ac7a3`: "Replace synthetic VCDs with real Xcelium -xprop F simulations"), the X propagation was much more realistic and several tests that passed with synthetic VCDs exposed new tracer issues.

### The Deep Pipeline Problem

The deep_pipeline test injected X at stage 0 of a 104-stage pipeline. The tracer was expected to trace all the way back: stage 104 -> stage 103 -> ... -> stage 0 -> primary input.

It stopped at stage 98.

The problem: by the time the tracer queried the signal at the query time T, the X pulse had already propagated past the early pipeline stages. Stage 98's D input showed 0 at time T (the X had already moved downstream). Stage 98's Q was still X (it captured the X earlier), but D was no longer X at the last clock edge before T.

The tracer was asking the right question at the wrong time.

The solution was **temporal backtrack**: when D is not X at the last clock edge before the query time, find when Q *first* became X (using `vcd.first_x_time()`), then look at D at that earlier clock edge. The X must have been on D at the edge that caused Q to first become X.

From `core.py`, lines 355-391 (the temporal backtrack logic):
```python
# Temporal backtrack: find when Q first became X and trace D at that edge.
q_first_x = None
for q_pname, q_pin in gate.outputs.items():
    # ... find earliest X time across wire and port signals
    t_x = vcd.first_x_time(try_sig, try_bit)
    if t_x is not None and (q_first_x is None or t_x < q_first_x):
        q_first_x = t_x

if q_first_x is not None and q_first_x < time:
    earlier_edge = _find_last_clock_edge(gate, vcd, q_first_x)
    # ... sample D at earlier_edge, trace from there
```

Result: the tracer now follows all 104 pipeline stages back to `ff_q_0`. Commit `7304499`: "Temporal backtrack: trace always reaches root cause through pipeline stages."

---

## Phase 7: SoC Integration -- Where Everything Breaks Again

The real test was always the ARM A55 SoC. 3.3 million gates. 28 million VCD signals. 5.5GB waveform files.

### VCD Loading at Scale

The Python VCD parser simply could not handle 28 million signals. Even cone-based loading (extracting only the backward cone of the query signal) took too long with Python string parsing. The Rust streaming VCD extractor (Phase 4, Attempt 3) was the solution -- 50 seconds for the full 5.5GB file.

### The Deposit Script Bug

X injection into the SoC used TCL deposit scripts sourced during Xcelium simulation. The first batch of tests produced puzzling results: no X propagation at all, despite explicit `force` commands in the TCL.

The problem was in `deposit_27dec.tcl`: it included a `run` command at the end. When sourced during simulation, this `run` command caused the simulation to advance to completion *before* the forces in the main testbench took effect. All the `force` commands happened after the simulation was already done.

The fix: source deposit scripts without a trailing `run`, following the same pattern used by the working JTAG and SRAM injection scripts.

### JTAG Injection -- A Dead End

The first SoC injection target was JTAG (specifically the `SWDIOTMS` signal). The trace returned `primary_input` immediately -- not because the tracer found the root cause, but because `SWDIOTMS` was *already* X. The testbench never drove it. There was no X to trace because the X was native to the signal.

The pivot was to GPIO and reset injections, where the testbench actively drives signals and the forced X has a clear propagation path through real logic.

### Multi-Bit DFF Port Mapping

The first GPIO trace stopped at a synchronization flip-flop, returning `uninit_ff` instead of tracing through to the root cause. The DFF was a `DFFQNAA2W` -- a multi-bit DFF with ports `D0`, `QN0`, `D1`, `QN1`.

The tracer's generic sequential handler used `gate.d_port` (which defaulted to `D1`) for all outputs. When tracing `QN0`, it checked `D1` -- the wrong D input. `D1` was not X, so the tracer concluded the FF was uninitialized and stopped.

The fix matches D ports to Q outputs by suffix index: `QN0` maps to `D0`, `Q1` maps to `D1`. From `core.py`, lines 275-289:

```python
# For multi-bit DFFs (e.g. DFFQNAA2W with D0/QN0, D1/QN1), match the
# D port to the Q output being traced by suffix index.
for q_pname, q_pin in gate.outputs.items():
    q_sig_check, q_bit_check = _pin_signal_bit(q_pin)
    if q_sig_check == signal and q_bit_check == bit:
        q_idx = re.search(r'(\d+)$', q_pname)
        if q_idx:
            candidate_d = f"D{q_idx.group(1)}"
            if candidate_d in gate.inputs:
                d_port = candidate_d
        break
```

### Escaped Identifiers

Even with the port mapping fixed, some signals were not found in the VCD. The netlist contained instances like `CDN_MBIT_ff_sync`, but the Xcelium VCD dumped them as `\CDN_MBIT_ff_sync` (with a backslash escape, standard for Verilog identifiers containing special characters). The netlist parser stripped the backslash; the VCD kept it.

The `_escaped_alt()` helper function tries both forms: if `a.b.CDN_MBIT_foo.D` is not found in the VCD, try `a.b.\CDN_MBIT_foo.D`.

### The Result

Commit `6b45b55`: "Multi-bit DFF port mapping + escaped identifiers: full SoC root cause trace."

The GPIO trace followed a 19-hop path: from the GPIO synchronization register, through a DFF capture, through 14 buffer cells (`BUFFD1BWP140`), all the way back to `gpio_in_val[0]` -- a `primary_input`. The X entered at the pad, propagated through the buffer chain, was captured by the sync register, and appeared on the internal bus. Root cause found.

The final test suite: 26 SoC-level trace tests across 7 subsystems (GPIO, reset, clock, SRAM, bus fabric, interrupt controller, debug), covering all 5 cause types (`primary_input`, `uninit_ff`, `x_injection`, `sequential_capture`, `x_propagation`). Commit `03f6a0d`: "SoC integration tests: GPIO root cause + reset injection traces."

---

## Phase 8: End-of-Simulation Tracing -- The Clock Cycle Explosion

All previous testing traced X values shortly after injection. A natural question: what happens when you trace from the *end* of simulation, hundreds of clock cycles after the X was injected?

### The Hang

Running the LFSR stress test at t=2,105,000 (end of simulation, ~100 clock cycles after injection at t=1,080,000) with `--max-depth 500` caused the tracer to hang indefinitely. At `--max-depth 50` it returned in 0.8 seconds but every single leaf was `max_depth` -- zero useful information. At `--max-depth 100` it took 46 seconds. The growth was exponential.

The root cause was the interaction between sequential tracing and the LFSR feedback topology. When tracing a DFF's X output, the tracer finds D was X at the last clock edge, recurses into the combinational logic driving D, reaches upstream DFFs, traces *those* back one clock edge, and so on. In an LFSR with feedback, DFF_A traces to DFF_B traces back to DFF_A -- but at a different time. The `(signal, bit, time)` memoization key is unique for each clock edge, so the cache never hits. The three-color DFS only prevents revisiting the same node at the same time, not the same signal at a different time.

With 128 DFFs, XOR feedback, and 100 clock cycles between injection and query, the trace tree grows combinatorially: each DFF is explored once per clock cycle, and each exploration fans out to multiple upstream DFFs.

### Fix 1: D-Input Temporal Skip

The key insight: if a DFF's D input is X at the current clock edge, it was *also* X at every clock edge since the X first arrived. Walking back one clock cycle at a time produces the same root cause at every step -- it just takes 100 times longer to get there.

The first version used `vcd.first_x_time()` (already available from Phase 6's temporal backtrack) to jump directly to when D *first* became X, skipping all intermediate clock cycles. This transforms the trace from O(clock_cycles × DFFs) to O(DFFs) -- each DFF is visited at most once regardless of how many clock cycles have elapsed since injection.

### Fix 1a: The X Window Gap Problem

The initial `first_x_time()` approach had a subtle correctness bug, caught during human review. The question was simple: "Does the algorithm take into account the fact that D may have transitioned from X to a known value and then back to X before Q changed?" It did not. Consider a signal that goes X, returns to a known value, and then goes X again from a *different cause*:

```
t=100: D becomes X  (from cause A — e.g. src_a through a mux)
t=200: D becomes 0  (X clears — mux switches away from src_a)
t=500: D becomes X  (from cause B — e.g. src_b through the same mux)
t=600: clock edge captures X from D → Q becomes X
```

`first_x_time()` returns t=100 — the first time D was *ever* X. But the X at t=100 was a different event that cleared at t=200. The X that the DFF actually captured came from cause B at t=500. Tracing from t=100 leads to the wrong root cause.

The fix was a new VCD query: `find_x_start(signal, bit, at)`. Instead of finding the first X ever, it walks backward from the current time to find the start of the *current* X window — the transition where the signal went from a known value to X most recently before `at`. From `database.py`:

```python
def find_x_start(self, signal: str, bit: int, at: int) -> int | None:
    """Find the start of the X window containing time `at`."""
    # Find transition at or before `at`
    idx = bisect.bisect_right(times, at) - 1
    # Walk backward to find where this X window began
    for i in range(idx, 0, -1):
        bit_cur = _extract_bit(tlist[i][1], bit)
        bit_prev = _extract_bit(tlist[i - 1][1], bit)
        if bit_cur in ('x', 'z') and bit_prev not in ('x', 'z'):
            return tlist[i][0]  # non-X → X transition
```

A targeted test case (`x_window_gap`) was built to exercise this: a DFF with D driven by a mux between `src_a` and `src_b`. The testbench makes D go X from `src_a`, then known, then X from `src_b`, then a clock edge captures. The test asserts the tracer identifies `src_b` as the root cause, not `src_a`. With the old `first_x_time` approach, this test would fail.

### Fix 2: Signal-Level Memoization for Sequential Elements

The original `sig_memo` cache explicitly excluded sequential cause types (`sequential_capture`, `clock_x`, `async_control_x`, `uninit_ff`). This was conservative but prevented cross-time reuse for DFFs. With the temporal skip, most DFFs converge to similar first-X times, making signal-level memoization highly effective.

The exclusion was removed: `sig_memo` now caches all completed results (only `max_depth` is excluded, since a deeper trace might reach further). To prevent exponential blowup during JSON serialization (shared Python object references get expanded into full copies), reused nodes attach cached *leaf nodes* directly (flattened) instead of sharing the full subtree.

```python
leaf_cache: dict[tuple[str, int], list[XCause]] = {}

# On sig_memo reuse: attach flattened leaves, not the deep subtree
if sig_key in sig_memo:
    prev = sig_memo[sig_key]
    if prev.cause_type != 'max_depth':
        leaves = leaf_cache.get(sig_key, [])
        node = XCause(signal=sig_str, time=time,
                      cause_type=prev.cause_type,
                      gate=prev.gate, children=leaves)
```

### Result

| Query time | max_depth | Before fix | After fix |
|-----------|-----------|------------|-----------|
| t=1,225,000 (manifest) | 500 | 14 seconds | <1 second |
| t=2,105,000 (end-of-sim) | 50 | 0.8s, all `max_depth` leaves | 0.2s, `primary_input` leaf |
| t=2,105,000 (end-of-sim) | 100 | 46 seconds | 0.2s |
| t=2,105,000 (end-of-sim) | 500 | hung indefinitely | **0.22 seconds** |

At t=2,105,000 with `--max-depth 500`: 90 nodes, 1 leaf, `primary_input` at `tb.dut.inject_data[0]`. The correct root cause, found in 0.22 seconds regardless of how many clock cycles have elapsed since injection.

---

## Phase 9: CLI-First Testing

### The Mandate

A critical realization: unit tests that called `trace_x()` directly were not testing what the user actually runs. The CLI pipeline includes cone-based VCD loading (loading only signals in the backward cone of the query), VCD-to-netlist path mapping, bus-to-bit signal name resolution, and per-instance port signal discovery. Bugs in any of these stages were invisible to tests that bypassed the CLI.

This was proven when CLI-based testing immediately exposed two bugs that unit tests had missed:

1. **Cone-to-VCD name mismatch**: The netlist cone contained bit-indexed signals (`tb.dut.final_out[0]`) but the VCD used bus-level names (`tb.dut.final_out`). The VCD loader didn't find the signals, loaded an empty set, and the trace failed. Fix: when building the VCD cone, try stripping the bit index to match bus-level VCD names.

2. **Rust backend bus filtering bug**: `xtracer_vcd.extract_signals()` returned incorrect values for bus signals when filtering by signal set. Returned `0` when the actual value was `x`. Disabled as default backend; falls through to pywellen/pyvcd which work correctly.

### The Refactor

All 391 tests were refactored to invoke `python3 x_tracer.py` as a subprocess, parse JSON output, and assert on the result. No test calls `trace_x()` or any internal API directly.

Key helpers:
- `_run_cli()`: Executes the CLI, logs full output to `tests/logs/`, returns parsed JSON tree
- `_collect_leaves()`: Recursively collects leaf nodes from JSON cause tree
- `_run_case()`: Reads a test case's `manifest.json`, invokes CLI with the right arguments

```python
def _run_cli(netlist_files, vcd_path, signal, time_ps, ...):
    cmd = [sys.executable, str(ROOT / "x_tracer.py")]
    for nf in netlist_files:
        cmd += ["-n", str(nf)]
    cmd += ["-v", str(vcd_path), "-s", signal, "-t", str(time_ps),
            "-f", "json", "--max-depth", str(max_depth)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return json.loads(result.stdout)
```

---

## Phase 10: Interactive Mode

The batch tracer produces a complete cause tree, but debugging is rarely a straight line. Engineers want to inspect a signal, check its driver, look at the fanout, change the query time, and explore alternative paths -- all without restarting the tool.

### Design

The interactive mode (`--interactive` / `-i`) reuses the same internal functions as the batch tracer -- `_get_drivers`, `_vcd_get_bit`, `_pin_signal_bit`, `_find_last_clock_edge`, `find_x_start`, `GateModel.forward()`, `GateModel.backward_causes()` -- so there are no discrepancies between what the interactive session shows and what the batch trace computes. Built on Python's `cmd` module for readline support (history, tab completion).

The tracer maintains a stack of visited nodes. Each `step` pushes a new node; `back` pops one. At each node, the display shows:

- Signal name, value, and time
- Driver gate type, instance path, and **source file:line** in the netlist
- All input port values, with X-valued inputs highlighted
- For sequential elements: clock edge timing, D value at the edge vs. pre-edge
- Gate model evaluation: expected output and causal input ports

### Source Location Tracking

To support "show me where this gate is in the netlist," the `Gate` dataclass was extended with `source_file` and `source_line` fields. The fast regex parser (`fast_parser.py`) now tracks line numbers during parsing: it uses `enumerate(f, 1)` on the file iterator and records the line where each gate instantiation begins (including multi-line statements that span several lines via accumulation).

### Commands

| Command | Description |
|---------|-------------|
| `step [N]` | Step into X input (auto if only one, pick by index if multiple) |
| `back` | Go back one step |
| `info` | Show current node details (gate, inputs, outputs, model evaluation) |
| `drivers [sig]` | Show drivers with source file:line |
| `fanout [sig]` | Show loads / gates that read the signal |
| `value [sig] [t]` | Show signal value and nearby VCD transitions |
| `trace` | Show the trace path so far (stack) |
| `run [depth]` | Run full automatic trace from current point |
| `hierarchy [sig]` | Trace signal up through hierarchy to top-level port |
| `signals <pat>` | Search for signals matching a pattern |
| `goto <sig> [t]` | Jump to a different signal (starts fresh trace) |
| `time <t>` | Change query time for current signal |

The `step` command handles sequential elements correctly: for DFF D-inputs, it finds the last clock edge, applies pre-edge sampling (same as the batch tracer), and uses `find_x_start` for temporal skip -- all the same logic that makes the batch tracer produce correct results.

The `run` command bridges interactive and batch modes: from any point in the interactive trace, the user can run the full automatic trace to see all root causes, then continue stepping manually.

### Example Session

```
$ python3 x_tracer.py -n netlist.v -n tb.v -v sim.vcd -s "tb.dut.final_out" -t 25000 -i

Interactive X-Tracer
Query: tb.dut.final_out[0] = X @ t=25000 ps

============================================================
  Signal:   tb.dut.final_out[0]
  Value:    X
  Gate:     buf (tb.dut.g_out)
  Inputs:
    A            = X  (tb.dut.ff_q[0]) <-- X
  X-valued inputs (1):
    [0] A -> tb.dut.ff_q[0]
============================================================
xtrace> step
  Signal:   tb.dut.ff_q[0]
  Gate:     dff_r (tb.dut.ff0)
  Clock:    CLK = 1, Last edge: t=25000
  D input:  D = X @ t=24999 (pre-edge)
  X-valued inputs (1):
    [0] D -> tb.dut.mux_out[0]
xtrace> step
  Signal:   tb.dut.mux_out[0]      (temporal skip to t=18000)
  Gate:     or (tb.dut.g_mux)
  Inputs:
    A = 0  (tb.dut.mux_a_arm[0])
    B = X  (tb.dut.mux_b_arm[0]) <-- X
xtrace> trace
  [0] tb.dut.final_out[0] @ t=25000 via buf
    [1] tb.dut.ff_q[0] @ t=25000 via dff_r
      [2] tb.dut.mux_out[0] @ t=18000 via or  <-- current
xtrace> run
  Root causes:
    [primary_input] tb.dut.src_b[0] @ t=18000
```

---

## Lessons Learned

**Brainstorm agents solve hard problems.** When the LFSR feedback loop had me stuck, launching three parallel brainstorm agents and taking the consensus answer (pre-edge D sampling) broke the logjam. Two out of three agents converged on the same solution independently -- a strong signal that it was the right answer.

**Test the tool, not the library.** Unit tests that call internal functions miss entire categories of bugs. Cone-based VCD loading, signal name mapping, and path prefix translation all sit between the CLI and the tracer core. If tests don't go through the CLI, those layers are untested. Every test should invoke the same command the user runs.

**Blind validators catch what humans miss.** The drive strength regex bug (`[BM]` instead of `[A-Z]`) was invisible during development because the test circuits happened to use only B and M suffix cells. A validator agent running against the full cell library found it immediately.

**Real SoC VCDs are a different beast.** Bus-level values lag behind per-bit DFF outputs. Escaped identifiers appear without warning. Multi-bit DFFs have indexed port names. Event types crash Rust parsers. Every assumption validated on synthetic VCDs broke on real Xcelium output.

**Always trace to root cause.** Stopping at an intermediate flip-flop with `uninit_ff` is useless to the engineer. The temporal backtrack, multi-bit DFF fixes, and D-input temporal skip were all about the same thing: refusing to give up until the trace reaches a primary input, an injection point, or a true uninitialized register. The temporal skip was particularly important -- without it, tracing from end-of-simulation was impossible on feedback-heavy designs.

**Rust is not optional for VCD parsing at scale.** Python line-by-line parsing of a 5GB VCD takes over 2 minutes. The Rust streaming extractor does it in 50 seconds. For interactive debugging, that difference matters.

**License servers will ruin your day.** Hours lost to `CDS_LIC_FILE` not including the second server at `192.168.5.8`. Always verify license connectivity before starting a debug session that depends on simulation.

---

## By the Numbers

| Metric | Value |
|--------|-------|
| SoC gates | 3.3 million |
| Netlist file size | 480 MB |
| VCD file size | 5.5 GB |
| VCD signals | 28 million |
| Synthetic test cases | 384 |
| SoC integration tests | 26 |
| Total tests (all CLI-based) | 393 |
| Netlist parse time (pyslang) | 11 minutes |
| Netlist parse time (fast_parser) | ~5 minutes |
| VCD parse time (Python) | 2+ minutes |
| VCD parse time (Rust) | 50 seconds |
| LFSR stress test leaves (before fix) | 8,007 |
| LFSR stress test leaves (after fix) | 3,010 |
| LFSR stress test runtime (near injection) | 5 ms |
| LFSR end-of-sim trace (before temporal skip) | hung indefinitely |
| LFSR end-of-sim trace (after temporal skip) | 0.22 seconds |
| GPIO SoC trace hops | 19 |
| Deep pipeline stages traced | 104/104 |
| Interactive mode commands | 12 |
