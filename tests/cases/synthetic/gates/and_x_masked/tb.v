`timescale 1ns/1ps
module tb;
  reg a, b;
  wire y;

  and2 dut (.y(y), .a(a), .b(b));

  initial begin
    // Clean initial state: a=0, b=0
    a = 1'b0;
    b = 1'b0;
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
    // At t=10ns inject X on a; b=0 so y remains 0 (X masked)
    #10;
    force tb.dut.a = 1'bx;
    // Let combinational logic settle
    #10;
    $finish;
  end
endmodule
