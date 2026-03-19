`timescale 1ns/1ps
module bit_slice_dut (
    input  [15:0] bus,
    output out
);
  assign out = bus[8];
endmodule
