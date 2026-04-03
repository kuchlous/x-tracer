`timescale 1ns/1ps
module bit_interleave_dut (
    input  [3:0] a,
    input  [3:0] b,
    output [7:0] out
);
  buf g0(out[0], b[0]);
  buf g1(out[1], a[0]);
  buf g2(out[2], b[1]);
  buf g3(out[3], a[1]);
  buf g4(out[4], b[2]);
  buf g5(out[5], a[2]);
  buf g6(out[6], b[3]);
  buf g7(out[7], a[3]);
endmodule
