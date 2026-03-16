`timescale 1ns/1ps
module tb;
  reg a;
  wire y;

  reconverge dut(.y(y), .a(a));

  // VCD dump
  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    // Drive input to known value before injection
    a = 1'b0;
    #10;

    // === INJECTION: force a = X at t=10ns ===
    force tb.dut.a = 1'bx;
    #20;

    $finish;
  end

  // Hard timeout
  initial #100 $finish;
endmodule
