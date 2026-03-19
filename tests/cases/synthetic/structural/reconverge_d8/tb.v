`timescale 1ns/1ps
module tb;
  reg src = 1'b1;
  wire out;
  reconverge dut(.out(out), .src(src));
  initial begin $dumpfile("sim.vcd"); $dumpvars(0, tb); end
  initial begin
    #10;
    force tb.dut.src = 1'bx;
    #20;
    $finish;
  end
  initial #100 $finish;
endmodule
