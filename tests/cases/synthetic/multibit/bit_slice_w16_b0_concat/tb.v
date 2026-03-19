`timescale 1ns/1ps
module tb;
  reg [15:0] bus;
  wire [7:0] out;

  bit_slice_dut dut (
    .bus(bus),
    .out(out)
  );

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    bus = 16'b0;
    #10;
    force tb.dut.bus[0] = 1'bx;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
