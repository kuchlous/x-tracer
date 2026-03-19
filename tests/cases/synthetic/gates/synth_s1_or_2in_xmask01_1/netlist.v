`timescale 1ns/1ps
module gate_dut (y, a, b);
  output y;
  input a;
  input b;
  or g0 (y, a, b);
endmodule
