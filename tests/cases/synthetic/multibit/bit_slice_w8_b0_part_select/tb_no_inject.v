`timescale 1ns/1ps
module tb;
  reg [7:0] bus;
  wire [1:0] out;

  bit_slice_dut dut (
    .bus(bus),
    .out(out)
  );

  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    bus = 8'b0;
    #10;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
