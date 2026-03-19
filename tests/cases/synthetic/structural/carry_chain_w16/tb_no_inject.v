`timescale 1ns/1ps
module tb;
  reg [15:0] a = 16'b1111111111111111;
  reg [15:0] b = 16'b0000000000000000;
  reg cin = 1'b0;
  wire [15:0] sum;
  wire cout;
  carry_chain dut(.sum(sum), .cout(cout), .a(a), .b(b), .cin(cin));
  initial begin $dumpfile("sim_no_inject.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;

    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
