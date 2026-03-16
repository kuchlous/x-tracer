`timescale 1ns/1ps
module tb;
  reg clk, rst_n, d;
  wire q1;

  ff_chain dut(.q1(q1), .d(d), .clk(clk), .rst_n(rst_n));

  // VCD dump
  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  // Clock: period = 10ns, toggles every 5ns
  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    // Drive all inputs to known values
    d     = 1'b0;
    rst_n = 1'b0;

    // 8 posedge clk cycles with rst_n=0  (ff0=ff1=0)
    repeat(8) @(posedge clk);

    // Release reset, 8 more cycles to settle — design fully clean here
    rst_n = 1'b1;
    repeat(8) @(posedge clk);

    // === INJECTION: force X into ff0 state element ===
    // ($deposit not supported by Icarus Verilog; force achieves same semantics:
    //  state element becomes X, propagates normally through clocked chain)
    force tb.dut.ff0 = 1'bx;

    // 3 more posedge clock cycles:
    // cycle+1: ff1 captures ff0=X → ff1=X → q1=X
    // cycle+2,3: X persists
    repeat(3) @(posedge clk);

    $finish;
  end

  // Hard timeout
  initial #500 $finish;
endmodule
