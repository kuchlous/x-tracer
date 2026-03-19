`timescale 1ns/1ps
module gate_dut (output y, input a, b, c);
  wire w;
  nand g0 (w, a, b);
  nand g1 (y, w, c);
endmodule
