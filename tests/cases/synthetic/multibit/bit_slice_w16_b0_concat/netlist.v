`timescale 1ns/1ps
module bit_slice_dut (
    input  [15:0] bus,
    output [7:0] out
);
  buf g0(out[0], bus[0]);
  buf g1(out[1], bus[2]);
  buf g2(out[2], bus[4]);
  buf g3(out[3], bus[6]);
  buf g4(out[4], bus[8]);
  buf g5(out[5], bus[10]);
  buf g6(out[6], bus[12]);
  buf g7(out[7], bus[14]);
endmodule
