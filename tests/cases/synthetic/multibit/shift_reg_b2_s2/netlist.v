`timescale 1ns/1ps
// Black-box DFF with async active-low reset (leaf cell for x-tracer)
module dff_r(input CLK, input D, input RST_N, output Q);
endmodule

`timescale 1ns/1ps
module shift_reg_dut (
    input  clk,
    input  rst_n,
    output [7:0] q
);
  wire [7:0] sr;

  // Rotate left: sr[i] <= sr[i-1], sr[0] <= sr[7]
  dff_r ff0 (.CLK(clk), .D(sr[7]), .RST_N(rst_n), .Q(sr[0]));
  dff_r ff1 (.CLK(clk), .D(sr[0]), .RST_N(rst_n), .Q(sr[1]));
  dff_r ff2 (.CLK(clk), .D(sr[1]), .RST_N(rst_n), .Q(sr[2]));
  dff_r ff3 (.CLK(clk), .D(sr[2]), .RST_N(rst_n), .Q(sr[3]));
  dff_r ff4 (.CLK(clk), .D(sr[3]), .RST_N(rst_n), .Q(sr[4]));
  dff_r ff5 (.CLK(clk), .D(sr[4]), .RST_N(rst_n), .Q(sr[5]));
  dff_r ff6 (.CLK(clk), .D(sr[5]), .RST_N(rst_n), .Q(sr[6]));
  dff_r ff7 (.CLK(clk), .D(sr[6]), .RST_N(rst_n), .Q(sr[7]));

  buf g_q0(q[0], sr[0]);
  buf g_q1(q[1], sr[1]);
  buf g_q2(q[2], sr[2]);
  buf g_q3(q[3], sr[3]);
  buf g_q4(q[4], sr[4]);
  buf g_q5(q[5], sr[5]);
  buf g_q6(q[6], sr[6]);
  buf g_q7(q[7], sr[7]);
endmodule
