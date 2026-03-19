`timescale 1ns/1ps
module tb;
  reg clk = 0;
  reg rst_n = 0;
  reg d = 0;
  wire q_out;
  reset_chain dut(.clk(clk), .rst_n(rst_n), .d(d), .q_out(q_out));
  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
    $dumpvars(0, tb.dut.ff0);
    $dumpvars(0, tb.dut.ff1);
    $dumpvars(0, tb.dut.ff2);
    $dumpvars(0, tb.dut.ff3);
  end
  always #5 clk = ~clk;
  initial begin
    #80;
    rst_n = 1;
    d = 1;
    #120;
    $finish;
  end
  initial #5000 $finish;
endmodule
