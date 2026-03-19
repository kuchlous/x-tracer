`timescale 1ns/1ps
module bit_slice_dut (
    input  [7:0] bus,
    output [3:0] out
);
  assign out = {bus[6],bus[4],bus[2],bus[0]};
endmodule
