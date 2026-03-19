`timescale 1ns/1ps
module tb;
  reg in0 = 1'b0;
  reg in1 = 1'b0;
  reg in2 = 1'b0;
  reg in3 = 1'b0;
  reg in4 = 1'b0;
  reg in5 = 1'b0;
  reg in6 = 1'b0;
  reg in7 = 1'b0;
  wire [7:0] out;
  bus_encoder dut(.out(out), .in0(in0), .in1(in1), .in2(in2), .in3(in3), .in4(in4), .in5(in5), .in6(in6), .in7(in7));
  initial begin $dumpfile("sim.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;
    force tb.dut.in0 = 1'bx;
    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
