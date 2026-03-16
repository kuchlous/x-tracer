`timescale 1ns/1ps
module tb;
  reg clk, rst_n, d;
  wire q1;

  ff_chain dut(.q1(q1), .d(d), .clk(clk), .rst_n(rst_n));

  // VCD dump
  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
  end

  // Clock: period = 10ns, toggles every 5ns
  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    // Drive all inputs to known values
    d     = 1'b0;
    rst_n = 1'b0;

    // 8 posedge clk cycles with rst_n=0
    repeat(8) @(posedge clk);

    // Release reset, 8 more cycles to settle
    rst_n = 1'b1;
    repeat(8) @(posedge clk);

    // NO INJECTION — same timing as injection run

    // 3 more posedge clock cycles (same duration as injection run)
    repeat(3) @(posedge clk);

    $finish;
  end

  // Hard timeout
  initial #500 $finish;
endmodule
