`timescale 1ns/1ps
module tb;
  reg [7:0] input_a;
  reg [7:0] input_b;
  wire [7:0] out;

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
    input_a = 8'b00000000;
    input_b = 8'hff;
    #10;
    force tb.dut.input_a[0] = 1'bx;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
