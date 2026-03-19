`timescale 1ns/1ps
module partial_bus_gate_dut (
    input  [15:0] input_a,
    input  [15:0] input_b,
    output [15:0] out
);
  and g0 (out[0], input_a[0], input_b[0]);
  and g1 (out[1], input_a[1], input_b[1]);
  and g2 (out[2], input_a[2], input_b[2]);
  and g3 (out[3], input_a[3], input_b[3]);
  and g4 (out[4], input_a[4], input_b[4]);
  and g5 (out[5], input_a[5], input_b[5]);
  and g6 (out[6], input_a[6], input_b[6]);
  and g7 (out[7], input_a[7], input_b[7]);
  and g8 (out[8], input_a[8], input_b[8]);
  and g9 (out[9], input_a[9], input_b[9]);
  and g10 (out[10], input_a[10], input_b[10]);
  and g11 (out[11], input_a[11], input_b[11]);
  and g12 (out[12], input_a[12], input_b[12]);
  and g13 (out[13], input_a[13], input_b[13]);
  and g14 (out[14], input_a[14], input_b[14]);
  and g15 (out[15], input_a[15], input_b[15]);
endmodule
