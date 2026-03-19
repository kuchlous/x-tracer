`timescale 1ns/1ps
module tb;
  reg clk = 0;
  reg rst_n = 0;
  reg d = 0;
  wire q_out;
  ff_chain dut(.clk(clk), .rst_n(rst_n), .d(d), .q_out(q_out));
  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
    $dumpvars(0, tb.dut.ff0);
  end
  always #5 clk = ~clk;
  initial begin
    #80;
    rst_n = 1;
    d = 1;
    #80;
    force tb.dut.ff0.Q = 1'bx;
    #30;
    $finish;
  end
  initial #5000 $finish;
endmodule
