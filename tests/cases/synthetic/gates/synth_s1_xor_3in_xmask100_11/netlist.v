`timescale 1ns/1ps
module gate_dut (y, a, b, c);
  output y;
  input a;
  input b;
  input c;
  xor g0 (y, a, b, c);
endmodule
