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

## Lessons Learned

**Brainstorm agents solve hard problems.** When the LFSR feedback loop had me stuck, launching three parallel brainstorm agents and taking the consensus answer (pre-edge D sampling) broke the logjam. Two out of three agents converged on the same solution independently -- a strong signal that it was the right answer.

**Blind validators catch what humans miss.** The drive strength regex bug (`[BM]` instead of `[A-Z]`) was invisible during development because the test circuits happened to use only B and M suffix cells. A validator agent running against the full cell library found it immediately.

**Real SoC VCDs are a different beast.** Bus-level values lag behind per-bit DFF outputs. Escaped identifiers appear without warning. Multi-bit DFFs have indexed port names. Event types crash Rust parsers. Every assumption validated on synthetic VCDs broke on real Xcelium output.

**Always trace to root cause.** Stopping at an intermediate flip-flop with `uninit_ff` is useless to the engineer. The temporal backtrack and multi-bit DFF fixes were both about the same thing: refusing to give up until the trace reaches a primary input, an injection point, or a true uninitialized register.

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
| Netlist parse time (pyslang) | 11 minutes |
| Netlist parse time (fast_parser) | ~5 minutes |
| VCD parse time (Python) | 2+ minutes |
| VCD parse time (Rust) | 50 seconds |
| LFSR stress test leaves (before fix) | 8,007 |
| LFSR stress test leaves (after fix) | 3,010 |
| LFSR stress test runtime | 5 ms |
| GPIO SoC trace hops | 19 |
| Deep pipeline stages traced | 104/104 |
