`timescale 1ns/1ps
module tb;
  reg [3:0] a;
  reg [3:0] b;
  wire [7:0] out;

  bit_interleave_dut dut (
    .a(a),
    .b(b),
    .out(out)
  );

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    a = 4'b0;
    b = 4'b0;
    #10;
    force tb.dut.b[2] = 1'bx;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
