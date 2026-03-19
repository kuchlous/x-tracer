`timescale 1ns/1ps
module multibit_mux_dut (
    input  [7:0] data_a,
    input  [7:0] data_b,
    input  sel,
    output [7:0] out
);
  assign out[0] = sel ? data_b[0] : data_a[0];
  assign out[1] = sel ? data_b[1] : data_a[1];
  assign out[2] = sel ? data_b[2] : data_a[2];
  assign out[3] = sel ? data_b[3] : data_a[3];
  assign out[4] = sel ? data_b[4] : data_a[4];
  assign out[5] = sel ? data_b[5] : data_a[5];
  assign out[6] = sel ? data_b[6] : data_a[6];
  assign out[7] = sel ? data_b[7] : data_a[7];
endmodule
