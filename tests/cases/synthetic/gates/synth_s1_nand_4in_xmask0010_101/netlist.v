`timescale 1ns/1ps
module gate_dut (y, a, b, c, d);
  output y;
  input a;
  input b;
  input c;
  input d;
  nand g0 (y, a, b, c, d);
endmodule
