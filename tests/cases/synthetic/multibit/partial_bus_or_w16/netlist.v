`timescale 1ns/1ps
module partial_bus_gate_dut (
    input  [15:0] input_a,
    input  [15:0] input_b,
    output [15:0] out
);
  or g0 (out[0], input_a[0], input_b[0]);
  or g1 (out[1], input_a[1], input_b[1]);
  or g2 (out[2], input_a[2], input_b[2]);
  or g3 (out[3], input_a[3], input_b[3]);
  or g4 (out[4], input_a[4], input_b[4]);
  or g5 (out[5], input_a[5], input_b[5]);
  or g6 (out[6], input_a[6], input_b[6]);
  or g7 (out[7], input_a[7], input_b[7]);
  or g8 (out[8], input_a[8], input_b[8]);
  or g9 (out[9], input_a[9], input_b[9]);
  or g10 (out[10], input_a[10], input_b[10]);
  or g11 (out[11], input_a[11], input_b[11]);
  or g12 (out[12], input_a[12], input_b[12]);
  or g13 (out[13], input_a[13], input_b[13]);
  or g14 (out[14], input_a[14], input_b[14]);
  or g15 (out[15], input_a[15], input_b[15]);
endmodule
