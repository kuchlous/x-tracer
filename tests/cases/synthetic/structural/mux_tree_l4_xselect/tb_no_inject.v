`timescale 1ns/1ps
module tb;
  reg d0 = 1'b0;
  reg d1 = 1'b1;
  reg d2 = 1'b0;
  reg d3 = 1'b1;
  reg d4 = 1'b0;
  reg d5 = 1'b1;
  reg d6 = 1'b0;
  reg d7 = 1'b1;
  reg d8 = 1'b0;
  reg d9 = 1'b1;
  reg d10 = 1'b0;
  reg d11 = 1'b1;
  reg d12 = 1'b0;
  reg d13 = 1'b1;
  reg d14 = 1'b0;
  reg d15 = 1'b1;
  reg sel0 = 1'b0;
  reg sel1 = 1'b0;
  reg sel2 = 1'b0;
  reg sel3 = 1'b0;
  wire out;
  mux_tree dut(.out(out), .d0(d0), .d1(d1), .d2(d2), .d3(d3), .d4(d4), .d5(d5), .d6(d6), .d7(d7), .d8(d8), .d9(d9), .d10(d10), .d11(d11), .d12(d12), .d13(d13), .d14(d14), .d15(d15), .sel0(sel0), .sel1(sel1), .sel2(sel2), .sel3(sel3));
  initial begin $dumpfile("sim_no_inject.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;

    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
