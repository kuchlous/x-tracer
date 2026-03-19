`timescale 1ns/1ps
module partial_bus_gate_dut (
    input  [7:0] input_a,
    input  [7:0] input_b,
    output [7:0] out
);
  and g0 (out[0], input_a[0], input_b[0]);
  and g1 (out[1], input_a[1], input_b[1]);
  and g2 (out[2], input_a[2], input_b[2]);
  and g3 (out[3], input_a[3], input_b[3]);
  and g4 (out[4], input_a[4], input_b[4]);
  and g5 (out[5], input_a[5], input_b[5]);
  and g6 (out[6], input_a[6], input_b[6]);
  and g7 (out[7], input_a[7], input_b[7]);
endmodule
