`timescale 1ns/1ps
module tb;
  reg d0 = 1'b0;
  reg d1 = 1'b0;
  reg d2 = 1'b0;
  reg d3 = 1'b0;
  reg d4 = 1'b0;
  reg d5 = 1'b0;
  reg d6 = 1'b0;
  reg d7 = 1'b0;
  reg sel0 = 1'b0;
  reg sel1 = 1'b0;
  reg sel2 = 1'b0;
  wire out;
  mux_tree dut(.out(out), .d0(d0), .d1(d1), .d2(d2), .d3(d3), .d4(d4), .d5(d5), .d6(d6), .d7(d7), .sel0(sel0), .sel1(sel1), .sel2(sel2));
  initial begin $dumpfile("sim_no_inject.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;

    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
