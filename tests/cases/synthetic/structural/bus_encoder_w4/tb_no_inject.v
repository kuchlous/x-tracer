`timescale 1ns/1ps
module tb;
  reg in0 = 1'b0;
  reg in1 = 1'b0;
  reg in2 = 1'b0;
  reg in3 = 1'b0;
  wire [3:0] out;
  bus_encoder dut(.out(out), .in0(in0), .in1(in1), .in2(in2), .in3(in3));
  initial begin $dumpfile("sim_no_inject.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;

    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
