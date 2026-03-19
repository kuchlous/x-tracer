`timescale 1ns/1ps
module tb;
  reg [3:0] a = 4'b1111;
  reg [3:0] b = 4'b0000;
  reg cin = 1'b0;
  wire [3:0] sum;
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
