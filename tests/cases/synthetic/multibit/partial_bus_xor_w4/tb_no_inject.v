`timescale 1ns/1ps
module tb;
  reg [3:0] input_a;
  reg [3:0] input_b;
  wire [3:0] out;

  partial_bus_gate_dut dut (
    .input_a(input_a),
    .input_b(input_b),
    .out(out)
  );

  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    input_a = 4'b0000;
    input_b = 4'h0;
    #10;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
