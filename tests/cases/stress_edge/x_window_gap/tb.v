`timescale 1ns/1ps

module tb;
  reg clk = 0;
  reg rst_n = 1;
  reg src_a = 0;
  reg src_b = 0;
  reg sel = 0;
  wire final_out;

  x_window_gap_net dut(
    .clk(clk), .rst_n(rst_n),
    .src_a(src_a), .src_b(src_b), .sel(sel),
    .final_out(final_out)
  );

  // 10ns clock period (posedge at 5, 15, 25, 35, 45, 55, ...)
  always #5 clk = ~clk;

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    // t=0: sel=0 -> mux selects src_a (=0). D=0.
    // t=2: src_a goes X. sel=0 -> D=X. (First X window, cause=src_a)
    #2;
    src_a = 1'bx;

    // t=5: posedge clk. D=X (from src_a). FF captures X -> Q=X.
    //       (This is the first X capture, but we care about the second.)

    // t=8: src_a returns to known. D becomes known again.
    #6;
    src_a = 1'b1;

    // t=12: switch mux to src_b. sel=1 -> D = src_b = 0. D is known.
    #4;
    sel = 1;

    // t=18: src_b goes X. sel=1 -> D=X. (Second X window, cause=src_b)
    #6;
    src_b = 1'bx;

    // t=25: posedge clk. D=X (from src_b). FF captures X -> Q=X.
    //       Query at t=25ns = 25000ps. Root cause should be src_b.

    #12;
    $finish;
  end

  initial #100 $finish;
endmodule
