`timescale 1ns/1ps
module tb;
  reg [7:0] bus;
  wire reduced_out;

  reduction_dut dut (
    .bus(bus),
    .reduced_out(reduced_out)
  );

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    bus = 8'b11111110;
    #10;
    force tb.dut.bus[0] = 1'bx;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
