`timescale 1ns/1ps
module gate_dut (output y, input a, b, c);
  wire w;
  or g0 (w, a, b);
  or g1 (y, w, c);
endmodule
