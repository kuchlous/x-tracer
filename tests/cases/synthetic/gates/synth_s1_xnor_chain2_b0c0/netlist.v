`timescale 1ns/1ps
module gate_dut (output y, input a, b, c);
  wire w;
  xnor g0 (w, a, b);
  xnor g1 (y, w, c);
endmodule
