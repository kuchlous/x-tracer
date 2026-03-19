`timescale 1ns/1ps
module tb;
  reg [3:0] data_a;
  reg [3:0] data_b;
  reg sel;
  wire [3:0] out;

  multibit_mux_dut dut (
    .data_a(data_a),
    .data_b(data_b),
    .sel(sel),
    .out(out)
  );

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    data_a = 4'b0;
    data_b = 4'b0;
    sel    = 1'b1;
    #10;
    force tb.dut.data_b[0] = 1'bx;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
