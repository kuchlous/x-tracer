`timescale 1ns/1ps
module gate_dut (output y, input a, b, c);
  wire w;
  nor g0 (w, a, b);
  nor g1 (y, w, c);
endmodule
