`timescale 1ns/1ps
module tb;
  reg a;
  wire y;

  reconverge dut(.y(y), .a(a));

  // VCD dump
  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    // Drive input to known value — NO injection
    a = 1'b0;
    #10;

    // NO INJECTION — same duration
    #20;

    $finish;
  end

  // Hard timeout
  initial #100 $finish;
endmodule
