`timescale 1ns/1ps
// Simple DFF with async active-low reset for gate-level simulation
module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

`timescale 1ns/1ps
module reset_chain(input clk, rst_n, d, output q_out);
  wire q0;
  dff_r ff0 (.CLK(clk), .D(d), .RST_N(rst_n), .Q(q0));
  dff_r ff1 (.CLK(clk), .D(q0), .RST_N(rst_n), .Q(q1));
  assign q_out = q1;
endmodule
