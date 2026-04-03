# X-Tracer

Root-cause analysis for X (unknown) values in Verilog gate-level simulations.

Given a gate-level netlist, a VCD waveform, and a signal that is `X` at a
specific time, X-Tracer traces backward through the netlist to produce a
**cause tree** — a complete explanation of where the X originated.

No open-source tool for this exists.

## Features

- **Backward X-tracing** through combinational and sequential logic
- **Bit-level precision** — tracks individual bits through buses, muxes, and bit slices
- **Cause tree output** — shows the full chain from query signal to root cause
- **Gate model** with IEEE 1364 X-propagation rules, including controlling-value masking
- **Standard cell support** — strips PDK prefixes and drive strength suffixes to recognize base cell functions (tested with Sky130)
- **Sequential handling** — traces through DFFs and latches with correct clock edge timing
- **Multiple output formats** — text (human-readable), JSON (machine-readable), DOT (Graphviz)
- **Fast VCD parsing** — Rust-backed pywellen for large files, pure-Python pyvcd fallback
- **Full SystemVerilog parsing** — pyslang handles any construct without crashing

## Root Cause Types

| Type | Meaning |
|------|---------|
| `primary_input` | Signal has no driver — X enters at the design boundary |
| `uninit_ff` | Flip-flop/latch was never initialized |
| `x_injection` | X was externally injected (force/deposit) — driver output disagrees with VCD |
| `sequential_capture` | FF captured X from its D input at a clock edge |
| `clock_x` | Clock/enable signal is X — FF output becomes X |
| `async_control_x` | Async reset or set is X |
| `multi_driver` | Multiple drivers on a net produce unresolvable X |
| `x_propagation` | X propagated through a combinational gate (intermediate node) |
| `unknown_cell` | Cell type not recognized — conservative fallback used |

## Installation

Requires Python 3.10+ and a C++ compiler (for pyslang wheels).

```bash
# Clone
git clone https://github.com/<your-org>/x-tracer.git
cd x-tracer

# Install dependencies
pip install pyslang pyvcd click

# Optional: install pywellen for fast VCD parsing (10-50x faster)
# Requires Rust toolchain (https://rustup.rs) and maturin
git clone https://github.com/kuchlous/wellen.git
cd wellen/pywellen
pip install maturin
maturin develop
cd ../..

# Verify
python3 -m pytest tests/test_*.py -q
```

## Usage

```bash
python3 x_tracer.py \
  -n <netlist.v> [-n <cells.v> ...] \
  -v <sim.vcd> \
  -s <signal> \
  -t <time_ps> \
  [-f text|json|dot] \
  [--max-depth 100]
```

### Arguments

| Flag | Description |
|------|-------------|
| `-n, --netlist` | Verilog netlist file(s). Pass multiple times for multiple files. Include the testbench if VCD paths use testbench hierarchy (e.g., `tb.dut.*`). |
| `-v, --vcd` | VCD waveform file from simulation |
| `-s, --signal` | Query signal in `path[bit]` format (e.g., `tb.dut.result[3]`) or scalar format (e.g., `tb.dut.clk`) |
| `-t, --time` | Query time in picoseconds |
| `-f, --format` | Output format: `text` (default), `json`, or `dot` |
| `--max-depth` | Maximum backward trace depth (default: 100) |
| `--top-module` | Top module name, auto-detected if omitted |

### Examples

**Trace an X through a combinational gate:**

```bash
python3 x_tracer.py \
  -n design.v -n tb.v \
  -v sim.vcd \
  -s "tb.dut.y[0]" -t 30000
```

```
[x_propagation] tb.dut.y[0] @ t=30000 (gate=and, inst=tb.dut.g0)
  [primary_input] tb.dut.b[0] @ t=30000
```

**Trace through a chain of flip-flops:**

```bash
python3 x_tracer.py \
  -n netlist.v -n tb.v \
  -v sim.vcd \
  -s "tb.dut.ff7.Q[0]" -t 240000
```

```
[sequential_capture] tb.dut.ff7.Q[0] @ t=240000 (gate=dff_r, inst=tb.dut.ff7)
  [sequential_capture] tb.dut.q6[0] @ t=235000 (gate=dff_r, inst=tb.dut.ff6)
    [sequential_capture] tb.dut.q5[0] @ t=225000 (gate=dff_r, inst=tb.dut.ff5)
      ...
              [uninit_ff] tb.dut.q0[0] @ t=175000 (gate=dff_r, inst=tb.dut.ff0)
```

**Trace reconvergent fanout (two paths from one source):**

```bash
python3 x_tracer.py \
  -n netlist.v -n tb.v \
  -v sim.vcd \
  -s "tb.dut.out[0]" -t 30000
```

```
[x_propagation] tb.dut.out[0] @ t=30000 (gate=and, inst=tb.dut.merge_gate)
  [x_propagation] tb.dut.a3[0] @ t=30000 (gate=buf, inst=tb.dut.ga3)
    ...
          [primary_input] tb.dut.src[0] @ t=30000
  [x_propagation] tb.dut.b3[0] @ t=30000 (gate=buf, inst=tb.dut.gb3)
    ...
          [primary_input] tb.dut.src[0] @ t=30000
```

**JSON output for scripting:**

```bash
python3 x_tracer.py -n design.v -n tb.v -v sim.vcd \
  -s "tb.dut.y[0]" -t 30000 -f json | python3 -m json.tool
```

**DOT output for visualization:**

```bash
python3 x_tracer.py -n design.v -n tb.v -v sim.vcd \
  -s "tb.dut.y[0]" -t 30000 -f dot | dot -Tpng -o trace.png
```

## Important Notes

### Include the testbench

If your VCD uses testbench hierarchy (signal paths like `tb.dut.signal`),
you must include the testbench file with `-n tb.v` so the parser builds the
correct hierarchy. Without it, the netlist paths won't match the VCD paths
and you'll get:

```
Error: Signal 'tb.dut.sig' found in VCD but not in the netlist.
Try including the testbench file with -n tb.v
```

### Cell libraries

For post-synthesis netlists that instantiate standard cells (e.g.,
`sky130_fd_sc_hd__and2_1`), the parser works in two modes:

1. **With cell library Verilog**: Pass the cell model files with `-n cells.v`.
   The parser extracts port directions from the cell definitions.

2. **Without cell library**: The parser infers port directions from naming
   conventions (Y/X/Z/Q are outputs, everything else is inputs). This works
   for most standard cell libraries but may mis-classify unusual port names.

### VCD requirements

- VCD must be generated with `$dumpvars(0, <top>)` to capture the full hierarchy
- For designs with sub-cells containing registers (DFFs), ensure internal signals
  are dumped (e.g., `$dumpvars(0, tb.dut.ff0)`)

## Architecture

```
┌──────────────┐    ┌──────────────┐
│ Netlist       │    │ VCD          │
│ Parser        │    │ Database     │
│ (pyslang)     │    │ (pywellen)   │
└──────┬───────┘    └──────┬───────┘
       │                    │
       ▼                    ▼
┌──────────────────────────────────┐
│ Connectivity Graph (plain dicts) │
│ + Gate Model (table-driven)      │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│ X-Tracer Core Algorithm          │
│ BFS backward through input cone  │
│ Memoized (signal, time) pairs    │
│ Sequential: async → clock → D    │
└──────────────┬───────────────────┘
               │
               ▼
         XCause tree → text/json/dot
```

### Modules

| Module | Location | Purpose |
|--------|----------|---------|
| Netlist Parser | `src/netlist/` | pyslang-based Verilog parser → connectivity graph |
| VCD Database | `src/vcd/` | Waveform loading with O(log n) time-value lookup |
| Gate Model | `src/gates/` | X-propagation rules for 30+ gate/cell types |
| Tracer Core | `src/tracer/` | Backward tracing algorithm with cause tree construction |
| CLI | `src/cli/` | Command-line interface and output formatters |

## Testing

The project includes a golden testcase suite (392 cases) covering:

- **S1 (gates)**: Every Verilog primitive with all relevant input combinations (302 cases)
- **S2 (structural)**: Carry chains, FF chains, reconvergent fanout, mux trees, reset chains, bus encoders (23 cases)
- **S3 (multibit)**: Partial bus injection, bit slicing, shift registers, reduction operators (67 cases)

```bash
# Run all unit + integration tests
python3 -m pytest tests/test_*.py -v

# Run the testcase validator (checks all golden cases)
python3 tests/validate.py
```

## Limitations (v1)

- No timing violation analysis (specify/notifier-based X)
- No strength resolution (4-state only, not 8-strength)
- No delta-cycle race detection
- Hard macros / black boxes reported as `unknown_cell`
- No UPF/CPF power intent support
- No bidirectional pad analysis

See `docs/SEMANTIC_SPEC.md` for the full specification.

## License

MIT
