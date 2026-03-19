`timescale 1ns/1ps
module tb;
  reg [31:0] a = 32'b11111111111111111111111111111111;
  reg [31:0] b = 32'b00000000000000000000000000000000;
  reg cin = 1'b0;
  wire [31:0] sum;
  wire cout;
  carry_chain dut(.sum(sum), .cout(cout), .a(a), .b(b), .cin(cin));
  initial begin $dumpfile("sim.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;
    force tb.dut.cin = 1'bx;
    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
