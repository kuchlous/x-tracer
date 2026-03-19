`timescale 1ns/1ps
module tb;
  reg clk;
  reg rst_n;
  wire [7:0] q;

  shift_reg_dut dut (
    .clk(clk),
    .rst_n(rst_n),
    .q(q)
  );

  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
  end

  initial clk = 0;
  always #5 clk = ~clk;

  initial begin
    rst_n = 1'b0;
    repeat(8) @(posedge clk);
    rst_n = 1'b1;
    repeat(8) @(posedge clk);
    #1;
    repeat(4) @(posedge clk);
    #1;
    $finish;
  end

  initial #206 $finish;
endmodule
