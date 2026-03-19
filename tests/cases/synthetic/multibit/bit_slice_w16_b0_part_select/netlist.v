`timescale 1ns/1ps
module bit_slice_dut (
    input  [15:0] bus,
    output [1:0] out
);
  assign out = bus[1:0];
endmodule
