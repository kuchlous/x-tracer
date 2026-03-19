#!/usr/bin/env python3
"""Regenerate ff_chain and reset_chain testcases as gate-level netlists.

The original S2 agent produced RTL (always blocks) instead of gate-level.
This script rewrites them using a simple DFF cell module that pyslang
can parse and the tracer can handle.
"""

import json
import hashlib
import subprocess
from pathlib import Path

CASES = Path("/home/ubuntu/x-tracer/tests/cases/synthetic/structural")

# A simple gate-level DFF cell with async reset, compatible with iverilog.
# The tracer recognizes it as sequential via "dff" in the name.
DFF_CELL = """\
`timescale 1ns/1ps
// Simple DFF with async active-low reset for gate-level simulation
module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule
"""

# DFF without reset
DFF_CELL_NORST = """\
`timescale 1ns/1ps
module dff(input CLK, input D, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK)
    Q <= D;
endmodule
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_and_sim(case_dir: Path, tb_name: str, vcd_name: str):
    vvp = case_dir / f"{tb_name}.vvp"
    files = [case_dir / f"{tb_name}.v", case_dir / "netlist.v"]

    r = subprocess.run(
        ["iverilog", "-o", str(vvp)] + [str(f) for f in files],
        capture_output=True, text=True, cwd=str(case_dir))
    if r.returncode != 0:
        print(f"  COMPILE FAIL ({tb_name}): {r.stderr.strip()}")
        return False

    r = subprocess.run(["vvp", str(vvp)], capture_output=True, text=True, cwd=str(case_dir))
    vvp.unlink(missing_ok=True)
    if not (case_dir / vcd_name).exists():
        print(f"  SIM FAIL ({tb_name}): VCD not produced")
        return False
    return True


def gen_ff_chain(depth: int):
    """Generate gate-level ff_chain with explicit DFF instances."""
    case_dir = CASES / f"ff_chain_d{depth}"
    case_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating ff_chain_d{depth}...")

    # Netlist: DFF cell + chain of dff_r instances
    lines = [DFF_CELL]
    lines.append("`timescale 1ns/1ps")
    lines.append(f"module ff_chain(input clk, rst_n, d, output q_out);")
    for i in range(depth):
        d_sig = "d" if i == 0 else f"q{i-1}"
        q_sig = f"q{i}"
        if i < depth - 1:
            lines.append(f"  wire {q_sig};")
        lines.append(f"  dff_r ff{i} (.CLK(clk), .D({d_sig}), .RST_N(rst_n), .Q({q_sig}));")
    lines.append(f"  assign q_out = q{depth-1};")
    lines.append("endmodule")
    (case_dir / "netlist.v").write_text("\n".join(lines) + "\n")

    # Testbench with injection
    inj_time_ns = 80 + 80  # 80 reset + 80 settle = 160ns
    query_time_ns = inj_time_ns + depth * 10  # depth clock cycles after injection
    wait_time = depth * 10 + 20

    # Build dumpvars lines for all FF internals
    dumpvars = "\n".join(f"    $dumpvars(0, tb.dut.ff{i});" for i in range(depth))

    tb = (
        "`timescale 1ns/1ps\n"
        "module tb;\n"
        "  reg clk = 0;\n"
        "  reg rst_n = 0;\n"
        "  reg d = 0;\n"
        "  wire q_out;\n"
        "  ff_chain dut(.clk(clk), .rst_n(rst_n), .d(d), .q_out(q_out));\n"
        "  initial begin\n"
        '    $dumpfile("sim.vcd");\n'
        "    $dumpvars(0, tb);\n"
        f"{dumpvars}\n"
        "  end\n"
        "  always #5 clk = ~clk;\n"
        "  initial begin\n"
        "    #80;\n"
        "    rst_n = 1;\n"
        "    d = 1;\n"
        "    #80;\n"
        "    force tb.dut.ff0.Q = 1'bx;\n"
        f"    #{wait_time};\n"
        "    $finish;\n"
        "  end\n"
        "  initial #5000 $finish;\n"
        "endmodule\n"
    )
    (case_dir / "tb.v").write_text(tb)

    # No-inject testbench
    tb_noinj = (
        "`timescale 1ns/1ps\n"
        "module tb;\n"
        "  reg clk = 0;\n"
        "  reg rst_n = 0;\n"
        "  reg d = 0;\n"
        "  wire q_out;\n"
        "  ff_chain dut(.clk(clk), .rst_n(rst_n), .d(d), .q_out(q_out));\n"
        "  initial begin\n"
        '    $dumpfile("sim_no_inject.vcd");\n'
        "    $dumpvars(0, tb);\n"
        f"{dumpvars}\n"
        "  end\n"
        "  always #5 clk = ~clk;\n"
        "  initial begin\n"
        "    #80;\n"
        "    rst_n = 1;\n"
        "    d = 1;\n"
        f"    #{80 + wait_time};\n"
        "    $finish;\n"
        "  end\n"
        "  initial #5000 $finish;\n"
        "endmodule\n"
    )
    (case_dir / "tb_no_inject.v").write_text(tb_noinj)

    # Compile and simulate
    if not compile_and_sim(case_dir, "tb", "sim.vcd"):
        return False
    if not compile_and_sim(case_dir, "tb_no_inject", "sim_no_inject.vcd"):
        return False

    # Manifest
    inj_time = inj_time_ns * 1000  # ps
    query_time = query_time_ns * 1000
    manifest = {
        "id": f"synth_s2_ff_chain_d{depth}",
        "category": "synthetic",
        "generation": "synthetic",
        "netlist": {"file": "netlist.v", "sha256": sha256(case_dir / "netlist.v"), "level": "gate"},
        "vcd": "sim.vcd",
        "no_inject_vcd": "sim_no_inject.vcd",
        "testbench": "tb.v",
        "sim_env": {"simulator": "iverilog", "version": "12.0", "timescale": "1ns/1ps"},
        "timing": {"clock_period_ticks": 10000, "clock_edge": "posedge"},
        "query": {"signal": f"tb.dut.ff{depth-1}.Q[0]", "time": query_time},
        "x_injection": {
            "method": "force", "target": "tb.dut.ff0.Q[0]",
            "value": "1'bx", "time": inj_time, "injection_class": "uninit_ff"
        },
        "expected": {
            "injection_target": "tb.dut.ff0.Q[0]",
            "injection_time": inj_time,
            "query_signal": f"tb.dut.ff{depth-1}.Q[0]",
            "query_time": query_time,
            "injection_class": "uninit_ff",
            "max_output": depth + 1
        },
        "status": "golden",
        "author": "agent-S2-fixed"
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  OK: query={manifest['expected']['query_signal']} @ t={query_time}")
    return True


def gen_reset_chain(reset_type: str, depth: int):
    """Generate gate-level reset_chain with explicit DFF instances."""
    case_dir = CASES / f"reset_chain_{reset_type}_d{depth}"
    case_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating reset_chain_{reset_type}_d{depth}...")

    # Netlist: DFF cell + chain of dff_r instances, reset signal is shared
    lines = [DFF_CELL]
    lines.append("`timescale 1ns/1ps")
    lines.append(f"module reset_chain(input clk, rst_n, d, output q_out);")
    for i in range(depth):
        d_sig = "d" if i == 0 else f"q{i-1}"
        q_sig = f"q{i}"
        if i < depth - 1:
            lines.append(f"  wire {q_sig};")
        lines.append(f"  dff_r ff{i} (.CLK(clk), .D({d_sig}), .RST_N(rst_n), .Q({q_sig}));")
    lines.append(f"  assign q_out = q{depth-1};")
    lines.append("endmodule")
    (case_dir / "netlist.v").write_text("\n".join(lines) + "\n")

    # Testbench — inject X on rst_n
    inj_time_ns = 160
    query_time_ns = 170
    dumpvars = "\n".join(f"    $dumpvars(0, tb.dut.ff{i});" for i in range(depth))

    tb = (
        "`timescale 1ns/1ps\n"
        "module tb;\n"
        "  reg clk = 0;\n"
        "  reg rst_n = 0;\n"
        "  reg d = 0;\n"
        "  wire q_out;\n"
        "  reset_chain dut(.clk(clk), .rst_n(rst_n), .d(d), .q_out(q_out));\n"
        "  initial begin\n"
        '    $dumpfile("sim.vcd");\n'
        "    $dumpvars(0, tb);\n"
        f"{dumpvars}\n"
        "  end\n"
        "  always #5 clk = ~clk;\n"
        "  initial begin\n"
        "    #80;\n"
        "    rst_n = 1;\n"
        "    d = 1;\n"
        "    #80;\n"
        "    force tb.dut.rst_n = 1'bx;\n"
        "    #40;\n"
        "    $finish;\n"
        "  end\n"
        "  initial #5000 $finish;\n"
        "endmodule\n"
    )
    (case_dir / "tb.v").write_text(tb)

    tb_noinj = (
        "`timescale 1ns/1ps\n"
        "module tb;\n"
        "  reg clk = 0;\n"
        "  reg rst_n = 0;\n"
        "  reg d = 0;\n"
        "  wire q_out;\n"
        "  reset_chain dut(.clk(clk), .rst_n(rst_n), .d(d), .q_out(q_out));\n"
        "  initial begin\n"
        '    $dumpfile("sim_no_inject.vcd");\n'
        "    $dumpvars(0, tb);\n"
        f"{dumpvars}\n"
        "  end\n"
        "  always #5 clk = ~clk;\n"
        "  initial begin\n"
        "    #80;\n"
        "    rst_n = 1;\n"
        "    d = 1;\n"
        "    #120;\n"
        "    $finish;\n"
        "  end\n"
        "  initial #5000 $finish;\n"
        "endmodule\n"
    )
    (case_dir / "tb_no_inject.v").write_text(tb_noinj)

    if not compile_and_sim(case_dir, "tb", "sim.vcd"):
        return False
    if not compile_and_sim(case_dir, "tb_no_inject", "sim_no_inject.vcd"):
        return False

    inj_time = inj_time_ns * 1000
    query_time = query_time_ns * 1000
    manifest = {
        "id": f"synth_s2_reset_chain_{reset_type}_d{depth}",
        "category": "synthetic",
        "generation": "synthetic",
        "netlist": {"file": "netlist.v", "sha256": sha256(case_dir / "netlist.v"), "level": "gate"},
        "vcd": "sim.vcd",
        "no_inject_vcd": "sim_no_inject.vcd",
        "testbench": "tb.v",
        "sim_env": {"simulator": "iverilog", "version": "12.0", "timescale": "1ns/1ps"},
        "timing": {"clock_period_ticks": 10000, "clock_edge": "posedge"},
        "query": {"signal": f"tb.dut.q_out[0]", "time": query_time},
        "x_injection": {
            "method": "force", "target": "tb.dut.rst_n",
            "value": "1'bx", "time": inj_time, "injection_class": "primary_input"
        },
        "expected": {
            "injection_target": "tb.dut.rst_n[0]",
            "injection_time": inj_time,
            "query_signal": "tb.dut.q_out[0]",
            "query_time": query_time,
            "injection_class": "primary_input",
            "max_output": depth + 2
        },
        "status": "golden",
        "author": "agent-S2-fixed"
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  OK: query={manifest['expected']['query_signal']} @ t={query_time}")
    return True


if __name__ == "__main__":
    ok = 0
    fail = 0
    for depth in [1, 2, 4, 8]:
        if gen_ff_chain(depth):
            ok += 1
        else:
            fail += 1

    for rst_type in ["async", "sync"]:
        for depth in [2, 4]:
            if gen_reset_chain(rst_type, depth):
                ok += 1
            else:
                fail += 1

    print(f"\nDone: {ok} OK, {fail} FAIL")
