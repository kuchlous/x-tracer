`timescale 1ns/1ps
module tb;
  reg d0 = 1'b0;
  reg d1 = 1'b1;
  reg d2 = 1'b0;
  reg d3 = 1'b1;
  reg sel0 = 1'b0;
  reg sel1 = 1'b0;
  wire out;
  mux_tree dut(.out(out), .d0(d0), .d1(d1), .d2(d2), .d3(d3), .sel0(sel0), .sel1(sel1));
  initial begin $dumpfile("sim_no_inject.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;

    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
