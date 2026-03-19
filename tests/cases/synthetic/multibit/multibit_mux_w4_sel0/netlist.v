`timescale 1ns/1ps
module multibit_mux_dut (
    input  [3:0] data_a,
    input  [3:0] data_b,
    input  sel,
    output [3:0] out
);
  assign out[0] = sel ? data_b[0] : data_a[0];
  assign out[1] = sel ? data_b[1] : data_a[1];
  assign out[2] = sel ? data_b[2] : data_a[2];
  assign out[3] = sel ? data_b[3] : data_a[3];
endmodule
