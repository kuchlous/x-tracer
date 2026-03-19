`timescale 1ns/1ps
module gate_dut (output y, input a, b, c);
  wire w;
  and g0 (w, a, b);
  and g1 (y, w, c);
endmodule
