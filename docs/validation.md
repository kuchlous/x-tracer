# X-Tracer Validation and Test Strategy

## 1. Test Strategy Overview

X-Tracer ships with **711 total tests**: 707 fast tests that complete in under 3 minutes, plus 4 SoC end-to-end tests that each take approximately 8 minutes. The tests are organized in a three-tier pyramid:

```
            +------------------+
            |  4 SoC E2E tests |   ~32 min (skipped in CI)
            +------------------+
         +------------------------+
         |  384 integration tests  |   ~2 min
         +------------------------+
      +------------------------------+
      |  243 unit tests + 16 fast    |   ~30 sec
      |  parser + 29 CLI + 35 stress |
      +------------------------------+
```

**Core invariant**: Every trace must reach a root cause. Leaf nodes must be `primary_input`, `x_injection` at the true source, or `uninit_ff` -- never an intermediate DFF or internal wire. This invariant is enforced in every test.

**Golden data**: Each synthetic test case stores a `manifest.json` with the query signal, query time, and expected injection target. Tests verify that the tracer's leaf nodes match the golden injection target.

---

## 2. Unit Tests

### 2.1 Gate Model (137 tests) -- `test_gates.py`

Tests the `GateModel` class covering `forward()` (compute output from inputs) and `backward_causes()` (identify which X-valued inputs are causal).

**Tier 1 -- Verilog Primitives (77 tests)**:

| Gate Type | Forward Tests | Backward Tests | Key Properties |
|-----------|--------------|----------------|----------------|
| `and`     | 9 (00,01,11,x0,0x,x1,xx,z1,z0) | 4 (x1,1x,xx,x0_masked) | Controlling value 0 masks X |
| `nand`    | 3 (11,x0,x1) | 2 (x1,x0_masked) | Inverted AND masking |
| `or`      | 7 (00,01,x1,1x,x0,xx,z0) | 3 (x0,x1_masked,xx) | Controlling value 1 masks X |
| `nor`     | 3 (00,x1,x0) | -- | Inverted OR masking |
| `xor`     | 6 (00,01,11,x0,x1,xx) | 3 (x0,x1,1x) | Never masks X |
| `xnor`    | 3 (00,01,x0) | -- | Never masks X |
| `not/buf` | 7 (not:0,1,x,z; buf:0,1,x) | 3 (not_x,not_0,buf_x) | Pass-through/invert |
| `bufif0/1, notif0/1` | 13 (tristate enable/disable) | 4 (data_x, en_x, both_x) | Enable-gated output |

**Tier 2 -- Standard Cells (28 tests)**:

- Cell name stripping: `sky130_fd_sc_hd__nand2_1` -> `nand2` (6 tests)
- `is_known_cell` for primitives, assign, and standard cells (14 tests)
- Standard cell forward/backward: `nand2_std`, `and2_std`, `inv_std`, `or3_std` (6 tests)
- z-as-x treatment: 3 tests confirming `z` is treated identically to `x`

**Tier 3 -- Complex Cells (32 tests)**:

- **AOI cells** (`a21oi`, `a22oi`): 7 tests -- AND-plane masking, OR-plane masking, X propagation, backward cause isolation
- **OAI cells** (`o21ai`): 4 tests -- OR-plane masking, AND-plane controlling value
- **MUX** (`mux2`): 6 tests -- select=0 passes A0, select=1 passes A1, select=X with same data is determined, backward cause for S=X
- **Adders** (`ha`, `fa`, `maj3`): 4 tests -- half adder, full adder, majority gate
- **Unknown cell fallback**: 5 tests -- conservative: any X input -> X output, all X ports returned as causes

**Standard Cell Recognition (16 tests)**:

- `strip_cell_name`: `AND2_X1M_A9PP140ZTH_C30` -> `and2`, handles drive suffixes (`X0P5B`, `X1M`)
- `identify_cell` for B/XB/BB suffixed cells: `NAND2B`, `AOI21B`, `OR2BB`, `NOR3B` recognized correctly
- `PREICG` clock gate recognition (2 tests)
- Multi-width DFFs: `DFFQAA2W`, `DFFQL4W` (2 tests)
- AO/OA families: `AO21`, `OA22` with correct group structure (2 tests)

### 2.2 VCD Database (24 tests) -- `test_vcd.py`

Tests the `VCDDatabase` abstraction over both pyvcd and pywellen backends.

| Test Area | Count | Coverage |
|-----------|-------|----------|
| `_extract_bit` helper | 5 | LSB, MSB, middle bits, MSB extension for short values |
| `get_value` scalar | 4 | Value at exact transition, between transitions, initial value |
| `get_value` bus | 3 | 4-bit bus with X bits, binary encoding |
| `get_bit` bus | 4 | Individual bit extraction from multi-bit signals at specific times |
| `get_bit` z-as-x | 1 | `z` value returned as `x` per spec |
| `first_x_time` | 3 | First X transition, X after time, no X after return to known |
| `find_edge` | 3 | Rising edge before time, falling edge before time, no edge found |
| Signal filtering | 2 | Load subset of signals, unloaded signals raise `KeyError` |
| Hierarchical paths | 1 | Multi-scope VCD with shared id_code across scopes |
| `get_transitions` | 1 | Full transition list for a signal |
| `get_all_signals` | 1 | Complete signal enumeration |
| Real VCD files | 4 | Load actual iverilog VCD, verify values, first_x, filtering |
| Backend fallback | 1 | pyvcd tokenizer fallback when pywellen unavailable |
| pywellen backend | 2 | Direct pywellen load and signal filtering (skipped if not installed) |

Timescale conversion is tested implicitly: VCDs use `1ps` timescale, and `first_x_time` / `find_edge` return times in VCD ticks.

### 2.3 Netlist Parser (37 tests) -- `test_netlist.py`

Tests the pyslang-based `parse_netlist` and fast regex-based `parse_netlist_fast`.

| Test Class | Count | Coverage |
|------------|-------|----------|
| `TestSimpleAnd` | 6 | Gate existence, cell_type, inputs (A,B), output (Y), drivers, fanout, not sequential |
| `TestGateChain` | 4 | AND->OR->NOT chain connectivity, input cone traversal, all signals enumeration |
| `TestDffWithReset` | 4 | Sequential detection, port roles (CLK, D, Q, RST), connections |
| `TestMultiDriver` | 1 | Two `bufif1` gates driving same net |
| `TestContinuousAssign` | 3 | `assign` gates, chain of assigns, input cone through assigns |
| `TestBitSelect` | 3 | Bit-level connections `y[0]`, `y[1]`, bit-level driver lookup |
| `TestSky130Dff` | 1 | `sky130_fd_sc_hd__dfxtp_1` recognized as sequential with correct port roles |
| `TestNandNorXor` | 1 | Verilog primitive cell_type preservation |
| `TestHierarchyMapping` | 10 | Sub-module instance path remapping, signal path remapping, deep nesting, driver/fanout lookup, input cone through hierarchy, sub-module instantiation as gate |
| `TestHierarchyAutoDetectTop` | 1 | Auto-detect top module (never-instantiated module) |
| `TestHierarchyNoSubModules` | 1 | Flat netlists pass through unmodified |
| `TestHierarchyMangledNames` | 3 | Innovus-style mangled module names (`soc_toparachne_amni_wdata_fmt_DW9`) correctly remapped |

Key capabilities validated:
- Escaped identifiers (`\name `) parsed and stripped
- Bit-select connections (`a[0]`, `y[1]`) tracked per-bit
- Hierarchy remapping: `sub_mod.u0` -> `top.inst_a.u0`
- Signal path remapping: `sub_a.w` -> `mytop.u_a.w`

### 2.4 Fast Parser (16 tests) -- `test_fast_parser.py`

Tests the regex-based `parse_netlist_fast` for flat post-P&R netlists.

| Test Class | Count | Coverage |
|------------|-------|----------|
| `TestFastParserBasic` | 3 | Single gate, multiple gates (AND2/OR2/INV), signal connectivity (drivers/fanout) |
| `TestFastParserEscapedIdentifiers` | 2 | Escaped instance names (`\u0_inst`), escaped signal names (`\net/abc`) |
| `TestFastParserMultiLine` | 2 | Multi-line AOI21 instantiation, multi-line OAI22 with 4+ ports |
| `TestFastParserPowerGround` | 2 | VDD/VSS ports filtered, VNW/VPW ports filtered |
| `TestFastParserSequentialDetection` | 3 | DFFR with CLK/D/Q/RST, DFFSET with CK/D/Q/SET, non-sequential AND2 not flagged |
| `TestFastParserHierarchy` | 2 | Sub-module remapping (`sub_mod.u0` -> `top.inst_a.u0`), auto-detect top |
| `TestFastParserAssign` | 2 | Simple assign, bus-indexed assign (`Y[0] = A`) |

Standard cell recognition: The fast parser handles named-port instantiations like `AND2_X1M_A9PP140ZTH_C30 u0 (.A(sig), .B(sig), .Y(out));` and correctly classifies output ports (Y, Z, ZN, Q, QN, S, CO, COUT) vs input ports.

### 2.5 CLI (29 tests) -- `test_cli.py`

Tests the `x_tracer.py` command-line interface end-to-end via `subprocess.run`.

| Test Class | Count | Coverage |
|------------|-------|----------|
| `TestTextFormat` | 1 | Text output contains cause_type brackets, signal paths, timestamps |
| `TestJsonFormat` | 2 | Valid JSON with signal/time/cause_type/children fields, correct query time |
| `TestDotFormat` | 1 | Graphviz DOT output with `digraph` and edges |
| `TestErrorCases` | 2 | Signal not X -> rc=1 with "not X" message; signal not found -> rc=1 with "not found" |
| `TestMultipleNetlists` | 1 | Two `--netlist` files (netlist.v + tb.v) |
| `TestStructural` | 2 | Bus encoder injection target in output, reconverge valid cause_type |
| `TestMultibit` | 1 | Bit-slice test case passes |
| `TestBulk` | 11 | Parametrized across 5 gate + 3 structural + 3 multibit cases; injection target signal appears in output |
| `TestFastParserFlag` | 2 | `--fast-parser` flag recognized (stderr message), works on structural case |
| `TestVCDTimescaleDisplay` | 2 | Stderr contains "VCD timescale:" with unit (fs/ps/ns/us/ms/s) |
| `TestQueryTimeDisplay` | 2 | Stderr contains "Query:" with ps and "VCD time:" |
| `TestVCDPrefix` | 2 | `--vcd-prefix tb.dut` with `--top-module top` maps paths correctly; stderr shows "Path mapping:" |

---

## 3. Integration Tests -- Synthetic Gate-Level Circuits

**384 tracer tests** across synthetic testcases in `tests/cases/synthetic/`, organized in three categories:

| Category | Test Cases | Description |
|----------|-----------|-------------|
| `gates/` | 302 | Single-gate and small gate combinations |
| `multibit/` | 49 | Multi-bit buses, bit-slice, partial bus operations |
| `structural/` | 23 | Multi-gate structures: bus encoders, reconvergent paths |

Each test case directory contains:
- `netlist.v` -- gate-level Verilog netlist
- `tb.v` -- testbench with X injection via `force` statement
- `sim.vcd` -- simulation waveform from iverilog
- `manifest.json` -- golden input/output specification

**manifest.json structure**:
```json
{
  "query": {"signal": "tb.dut.y[0]", "time": 30000},
  "expected": {"injection_target": "tb.dut.a[0]"}
}
```

**Test execution** (`TestBulk` in `test_tracer.py`):
1. Parse netlist from `netlist.v` + `tb.v`
2. Load VCD from `sim.vcd`
3. Run `trace_x()` with query signal and time from manifest
4. Collect all leaves from the cause tree
5. Assert: injection target from manifest appears in leaf signals

**Cause types covered across the 384 tests**:
- `primary_input` -- signal is a top-level input port
- `x_propagation` -- X propagated through combinational logic
- `x_injection` -- explicit X forced via testbench
- `uninit_ff` -- uninitialized flip-flop output
- `unknown_cell` -- cell type not in gate model (conservative)
- `max_depth` -- trace depth limit reached
- `clock_x` -- clock signal is X
- `no_driver` -- signal has no driving gate in netlist
- `unknown` -- fallback for unclassifiable causes

**Additional targeted tests**:
- `TestSingleGate`: AND gate with X on input, AND gate X propagation
- `TestChainCases`: Bus encoder (4-wide), reconvergent fanout (depth 2)
- `TestMultibit`: 16-bit slice select, 16-bit part select, 4-bit partial AND, 4-bit partial OR
- `TestEdgeCases`: `max_depth=1` cutoff produces `max_depth` leaves; querying non-X signal raises `ValueError`

---

## 4. Stress Tests -- LFSR Grid

**Design**: 2x2x2x2x8 LFSR grid (`tests/cases/stress/`)

| Parameter | Value |
|-----------|-------|
| Grid dimensions | 2 rows x 2 columns of clusters |
| Cluster structure | 2 stages x 2 lanes of 8-bit LFSRs |
| Total flip-flops | 128 DFFs |
| Total gates | 752 combinational gates |
| Total signals | ~1518 |
| Hierarchy depth | 2 levels (flattened) |
| Clock period | 10,000 ticks (10 ns at 1ns/1ps timescale) |

**Injection**: `force tb.dut.r0c0_s0l0_ff0.Q = 1'bx` at tick 1,090,000. The X propagates from `inject_data[0]` (primary input, tick 1,080,000) through the entire LFSR grid to `final_out[0]` at tick 1,225,000.

**Simulation**: Real Xcelium 24.09 with `-xprop F` (full X propagation). VCD generated by Xcelium, not synthetic.

**Test** (`test_lfsr_grid_trace_all_leaves_primary_input`):
- Uses `parse_netlist_fast` with `top_module="tb"`
- `max_depth=500` (far exceeds actual depth)
- Asserts: `len(leaves) > 0`
- Asserts: all leaf `cause_type` values are `"primary_input"` (no `max_depth` cutoffs)
- Asserts: all leaf signals are exactly `tb.dut.inject_data[0]` (single root cause)

**Validated properties**:
- Three-color DFS: cycle detection in reconvergent LFSR feedback paths
- Pre-edge D sampling: DFF data input sampled at clock edge preceding query time
- `sig_memo`: memoization prevents exponential blowup in reconvergent fanout
- **Result**: 3010 leaves, all `primary_input` at `inject_data[0]`, completes in ~5 ms

---

## 5. Edge Case Stress Tests

Five purpose-built designs in `tests/cases/stress_edge/`, each targeting a specific tracing challenge. All use real Xcelium VCDs with `force` injection and query on `tb.dut.final_out[0]`.

### 5.1 deep_pipeline (104-stage FF chain)

- **Design**: 104 flip-flops in series: `ff_q_0` -> `ff_q_1` -> ... -> `ff_q_103` -> `final_out`
- **Injection**: `force tb.dut.ff_q_0 = 1'bx` (first DFF in chain)
- **Challenge**: Temporal backtracking -- tracer must step backward through 104 clock edges, sampling D input at each preceding posedge
- **Assertion**: Exactly 1 leaf at `tb.dut.ff_q_0[0]`
- **Validates**: Deep temporal recursion, DFF clock edge detection over 104 hops

### 5.2 wide_fanout (32-way reconvergent)

- **Design**: Source DFF `src_q` fans out to 32 parallel buffer paths, all reconverging at `final_out`
- **Injection**: `force tb.dut.src_q = 1'bx`
- **Challenge**: Reconvergent fanout -- 32 independent paths from same source must all be traced
- **Assertion**: Exactly 32 leaves; at least 24 trace to `src_q` (root cause)
- **Validates**: Fanout handling, memoization correctness with shared source

### 5.3 clock_crossing (dual-clock CDC)

- **Design**: Two clock domains (A and B). DFF `a_q0` in domain A, synchronizer chain in domain B
- **Injection**: `force tb.dut.a_q0 = 1'bx` (DFF in domain A)
- **Challenge**: Cross-domain tracing -- tracer must follow X across clock domain boundary
- **Assertion**: Exactly 1 leaf at `tb.dut.a_q0[0]`
- **Validates**: Multi-clock tracing, correct clock edge detection per domain

### 5.4 tristate_bus (4-driver bufif1)

- **Design**: 4 `bufif1` tristate drivers on a shared bus, each with independent enable
- **Injection**: Force one driver's data to X while its enable is active
- **Challenge**: Identify which of the 4 drivers is active and causing X on the bus
- **Assertion**: At least 1 leaf; cause_type is `x_injection` or `uninit_ff`
- **Validates**: Tristate bus resolution, active driver identification

### 5.5 nested_clock_gate (3-level ICG)

- **Design**: 3 levels of integrated clock gating: `ICG_L1` -> `ICG_L2` -> `ICG_L3` -> DFF
- **Injection**: Force gated clock `gclk_l3` to X
- **Challenge**: Trace X through gated clock tree to identify gating source
- **Assertion**: Exactly 2 leaves; at least one of `tb.dut.gclk_l3[0]` or `tb.dut.qa[0]` present
- **Validates**: Clock gate tracing, ICG cell recognition (`PREICG` cells)

---

## 6. SoC End-to-End Tests

Real-world validation against a 22nm ARM Cortex-A55 SoC.

### 6.1 SoC Environment

| Parameter | Value |
|-----------|-------|
| Technology | 22nm (A9PP140ZTH/ZTL cells) |
| Design | ARM Cortex-A55 based SoC (`rjn_soc_top`) |
| Netlist | `rjn_soc_top.Fill_uniquify.v` -- 480 MB flat post-P&R |
| Top module | `rjn_soc_top` |
| VCD prefix | `rjn_top.u_rjn_soc_top` (VCD) -> `rjn_soc_top` (netlist) |
| Simulator | Xcelium with `-xprop F` |
| Parser | `parse_netlist_fast` (regex-based, handles 480 MB in ~60 sec) |

### 6.2 GPIO Injection Tests (TestSoCGPIOTrace)

**Scenario**: `APP_GPIO0` forced to X at 50 us via TCL script. X propagates through GPIO subsystem affecting 3428 signals across 4 subsystems.

**test_gpio_sync_register_traces_to_primary_input**:
- Query: `rjn_top.u_rjn_soc_top.inst_rjn_app_top.inst_app_gpio1.FE_OFC229639_gpio_ifc_rg_in_sync1_0.Y` at 55,000,000 ps (55 us)
- Expected: 19 hops through DFF + buffer tree back to `gpio_in_val[0]` as `primary_input`
- Trace path: buffer output -> DFF chain -> buffer tree -> `gpio_in_val[0]`
- Assertion: At least 1 `primary_input` leaf containing `gpio_in_val` in signal name

**test_gpio_port_traces_to_primary_input**:
- Query: `rjn_top.u_rjn_soc_top.APP_GPIO0` at 55,000,000 ps
- Expected: Direct `primary_input` (top-level port)
- Assertion: Exactly 1 leaf, `cause_type == "primary_input"`, signal contains `APP_GPIO0`

### 6.3 Reset Injection Tests (TestSoCResetTrace)

**Scenario**: `EXTERNAL_RESET` forced to X at 50 us. X propagates through reset distribution tree affecting 965,871 signals.

**test_reset_port_traces_to_primary_input**:
- Query: `rjn_top.u_rjn_soc_top.EXTERNAL_RESET` at 55,000,000 ps
- Expected: Direct `primary_input`
- Assertion: Exactly 1 leaf, `cause_type == "primary_input"`, signal contains `EXTERNAL_RESET`

**test_reset_buffer_tree_traces_to_primary_input**:
- Query: `rjn_top.u_rjn_soc_top.FE_OFN94700_EXTERNAL_RESET_fromPad` at 55,000,000 ps
- Expected: 3 hops through INV + BUF back to `EXTERNAL_RESET_fromPad` as `primary_input`
- Assertion: At least 1 `primary_input` leaf containing `EXTERNAL_RESET` in signal name

### 6.4 SoC Test Infrastructure

The SoC tests use cone-based VCD loading to handle the 5.5 GB VCD:

1. **Header-only load**: `load_vcd_header()` reads signal names and timescale without loading waveform data (~2 sec for 5.5 GB)
2. **Backward cone computation**: `netlist.get_input_cone()` identifies all signals in the transitive fanin of the query signal
3. **Selective VCD load**: Only signals in the cone are loaded from the VCD (reduces 28M signals to a few thousand)
4. **Prefix mapping**: `PrefixMappedVCD` transparently maps between VCD paths (`rjn_top.u_rjn_soc_top.*`) and netlist paths (`rjn_soc_top.*`)
5. **Per-instance port signals**: Gate input/output port signals (e.g., `inst.A`, `inst.Y`) are added to the cone for cells that have per-port VCD entries

---

## 7. Test Methodology

### 7.1 Real User Workflow

Tests mirror the actual debugging workflow:

1. **User runs simulation** with Xcelium `-xprop F` (full X propagation mode)
2. **User sees X** on a signal in the waveform viewer
3. **User identifies the deepest X signal** they care about
4. **User runs x-tracer** with `--signal`, `--time`, `--netlist`, `--vcd`
5. **Tool traces backward** through the netlist/VCD to find the root cause
6. **User gets root cause**: primary input port, uninitialized FF, or explicit injection point

### 7.2 Injection Methods

| Method | Used In | Description |
|--------|---------|-------------|
| Testbench `force` | All synthetic + stress tests | `force tb.dut.signal = 1'bx;` in Verilog testbench |
| TCL `force` | SoC tests | `force rjn_top.u_rjn_soc_top.APP_GPIO0 1'bx` via Xcelium TCL script |
| Uninitialized FF | Some gate tests | DFF output starts as X when no reset applied |
| Primary input X | LFSR stress test | `inject_data[0]` driven X from testbench |

### 7.3 Assertion Philosophy

Every test enforces the same core contract:

- **Every leaf must be a root cause**: `primary_input` (top-level port with no driver), `x_injection` at the true source signal, or `uninit_ff` at the originating flip-flop
- **No intermediate DFFs**: A DFF in the middle of a buffer tree is NOT a valid root cause. The tracer must continue through the DFF's D input at the preceding clock edge
- **No internal wires**: An internal wire that happens to be X is not a root cause. The tracer must follow it to its driving gate
- **Injection target match**: For all synthetic tests, the tracer's leaf signals must contain the `injection_target` from the golden manifest

### 7.4 VCD Data Provenance

| Test Tier | Simulator | X Propagation Mode | Notes |
|-----------|-----------|-------------------|-------|
| Synthetic gate tests | iverilog | Default (pessimistic) | Open-source, reproducible |
| LFSR stress test | Xcelium 24.09 | `-xprop F` (full) | Real commercial simulator |
| Edge case stress tests | Xcelium 24.09 | `-xprop F` (full) | Real commercial simulator |
| SoC tests | Xcelium | `-xprop F` (full) | Production simulation environment |

All stress and SoC VCDs are from real Xcelium simulations, not synthetically constructed. This ensures the tracer handles real-world VCD quirks (Cadence escaped identifiers, multi-driver nets, clock gating cells).

---

## 8. Known Limitations and Future Tests

### 8.1 Current Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| SoC tests require local netlist/VCD files | Skipped in CI with `@pytest.mark.skipif` | Run locally on machines with access to `/Backend_share` and `/data/work_area` |
| No SRAM injection tests | Cannot validate tracing through memory arrays | SRAM outputs treated as primary inputs (conservative) |
| No clock injection tests | Clock-as-X tracing only tested via nested_clock_gate edge case | `clock_x` cause type exists but not systematically tested |
| Multi-clock domain tracing limited | Only 2 domains tested (clock_crossing edge case) | Sufficient for current SoC designs with synchronizer chains |
| No formal verification of trace correctness | Trace results validated against golden manifests, not proven correct | Golden manifests are manually verified by designer |
| pywellen backend tests skipped without pywellen | 2 tests in `test_vcd.py` are skipped | pyvcd backend provides full coverage |
| Verilog primitives not supported in fast parser | Fast parser uses named-port regex; positional primitives require pyslang | Use `parse_netlist` (pyslang) for designs with Verilog primitives |

### 8.2 Future Test Additions

- **SRAM injection**: Trace X through memory read port to write port or address decode
- **Clock tree injection**: Systematic tests for X on clock at various points in clock distribution
- **3+ clock domain CDC**: Designs with 3 or more clock domains and multi-stage synchronizers
- **Latch transparency**: Trace through transparent latches (currently only DFFs tested)
- **Scan chain**: Trace X through scan insertion (JTAG/scan mode)
- **Power domain crossing**: Trace X through level shifters and isolation cells
- **Regression against more SoC blocks**: Extend SoC tests to cover CPU core, interconnect, and peripheral subsystems
- **Performance regression**: Track trace time and memory usage across releases for the LFSR stress test and SoC tests
