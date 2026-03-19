`timescale 1ns/1ps
module tb;
  reg [7:0] data_a;
  reg [7:0] data_b;
  reg sel;
  wire [7:0] out;

  multibit_mux_dut dut (
    .data_a(data_a),
    .data_b(data_b),
    .sel(sel),
    .out(out)
  );

  initial begin
    $dumpfile("sim_no_inject.vcd");
    $dumpvars(0, tb);
  end

  initial begin
    data_a = 8'b0;
    data_b = 8'b0;
    sel    = 1'b0;
    #10;
    #20;
    $finish;
  end

  initial #100 $finish;
endmodule
