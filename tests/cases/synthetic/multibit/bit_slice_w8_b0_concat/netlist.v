`timescale 1ns/1ps
module bit_slice_dut (
    input  [7:0] bus,
    output [3:0] out
);
  buf g0(out[0], bus[0]);
  buf g1(out[1], bus[2]);
  buf g2(out[2], bus[4]);
  buf g3(out[3], bus[6]);
endmodule
