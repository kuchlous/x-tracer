`timescale 1ns/1ps
module tb;
  reg a = 1'b0;
  reg b = 1'b1;
  wire y;
  gate_dut dut (.y(y), .a(a), .b(b));
  initial begin $dumpfile("sim_no_inject.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;

    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
