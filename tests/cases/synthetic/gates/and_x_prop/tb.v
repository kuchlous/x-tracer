`timescale 1ns/1ps
module tb;
  reg a, b;
  wire y;

  and2 dut (.y(y), .a(a), .b(b));

  initial begin
    // Clean initial state: all inputs known before injection
    a = 1'b0;
    b = 1'b1;
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
    // At t=10ns inject X on a; b=1 so y should go X
    #10;
    force tb.dut.a = 1'bx;
    // Let combinational logic settle
    #10;
    $finish;
  end
endmodule
