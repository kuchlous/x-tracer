`timescale 1ns/1ps
module bit_slice_dut (
    input  [15:0] bus,
    output [1:0] out
);
  // out = bus[9:8]
  buf g_out0(out[0], bus[8]);
  buf g_out1(out[1], bus[9]);
endmodule
