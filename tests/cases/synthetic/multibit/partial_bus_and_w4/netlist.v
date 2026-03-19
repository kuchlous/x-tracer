`timescale 1ns/1ps
module partial_bus_gate_dut (
    input  [3:0] input_a,
    input  [3:0] input_b,
    output [3:0] out
);
  and g0 (out[0], input_a[0], input_b[0]);
  and g1 (out[1], input_a[1], input_b[1]);
  and g2 (out[2], input_a[2], input_b[2]);
  and g3 (out[3], input_a[3], input_b[3]);
endmodule
