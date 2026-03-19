`timescale 1ns/1ps
module reduction_dut (
    input  [7:0] bus,
    output reduced_out
);
  assign reduced_out = ^bus;
endmodule
