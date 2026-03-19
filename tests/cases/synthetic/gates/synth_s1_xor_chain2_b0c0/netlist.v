`timescale 1ns/1ps
module gate_dut (output y, input a, b, c);
  wire w;
  xor g0 (w, a, b);
  xor g1 (y, w, c);
endmodule
