`timescale 1ns/1ps
// Black-box DFF with async active-low reset (leaf cell for x-tracer)
module dff_r(input CLK, input D, input RST_N, output Q);
endmodule

`timescale 1ns/1ps
module ff_chain(input clk, rst_n, d, output q_out);
  wire q0;
  dff_r ff0 (.CLK(clk), .D(d), .RST_N(rst_n), .Q(q0));
  buf g_out(q_out, q0);
endmodule
