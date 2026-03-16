`timescale 1ns/1ps
module tb;
  reg a, b;
  wire y;

  and2 dut (.y(y), .a(a), .b(b));

  initial begin
    a = 1'b0;
    b = 1'b1;
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
    // No injection — hold known values through the same window
    #20;
    $finish;
  end
endmodule
