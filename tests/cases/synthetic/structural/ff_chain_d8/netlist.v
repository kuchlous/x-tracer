`timescale 1ns/1ps
// Simple DFF with async active-low reset for gate-level simulation
module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

`timescale 1ns/1ps
module ff_chain(input clk, rst_n, d, output q_out);
  wire q0;
  dff_r ff0 (.CLK(clk), .D(d), .RST_N(rst_n), .Q(q0));
  wire q1;
  dff_r ff1 (.CLK(clk), .D(q0), .RST_N(rst_n), .Q(q1));
  wire q2;
  dff_r ff2 (.CLK(clk), .D(q1), .RST_N(rst_n), .Q(q2));
  wire q3;
  dff_r ff3 (.CLK(clk), .D(q2), .RST_N(rst_n), .Q(q3));
  wire q4;
  dff_r ff4 (.CLK(clk), .D(q3), .RST_N(rst_n), .Q(q4));
  wire q5;
  dff_r ff5 (.CLK(clk), .D(q4), .RST_N(rst_n), .Q(q5));
  wire q6;
  dff_r ff6 (.CLK(clk), .D(q5), .RST_N(rst_n), .Q(q6));
  dff_r ff7 (.CLK(clk), .D(q6), .RST_N(rst_n), .Q(q7));
  assign q_out = q7;
endmodule
