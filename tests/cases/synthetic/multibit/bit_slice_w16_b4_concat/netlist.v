`timescale 1ns/1ps
module bit_slice_dut (
    input  [15:0] bus,
    output [7:0] out
);
  assign out = {bus[14],bus[12],bus[10],bus[8],bus[6],bus[4],bus[2],bus[0]};
endmodule
