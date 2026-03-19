`timescale 1ns/1ps
module gate_dut (y, a);
  output y;
  input a;
  buf g0 (y, a);
endmodule
