`timescale 1ns/1ps
module tb;
  reg a = 1'b0;
  reg b = 1'b1;
  reg c = 1'b0;
  reg d = 1'b0;
  wire y;
  gate_dut dut (.y(y), .a(a), .b(b), .c(c), .d(d));
  initial begin $dumpfile("sim.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;
    force tb.dut.a = 1'bx;
    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
