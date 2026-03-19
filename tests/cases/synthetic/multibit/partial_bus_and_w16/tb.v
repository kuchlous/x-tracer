`timescale 1ns/1ps
module tb;
  reg [15:0] input_a;
  reg [15:0] input_b;
  wire [15:0] out;

  partial_bus_gate_dut dut (
    .input_a(input_a),
    .input_b(input_b),
    .out(out)
  );

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    input_a = 16'b0000000000000000;
    input_b = 16'hffff;
    #10;
    force tb.dut.input_a[0] = 1'bx;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
