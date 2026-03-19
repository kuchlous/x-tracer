`timescale 1ns/1ps
module mux_tree(output out, input d0, input d1, input d2, input d3, input sel0, input sel1);
  wire m0_0;
  assign m0_0 = sel0 ? d1 : d0;
  wire m0_1;
  assign m0_1 = sel0 ? d3 : d2;
  assign out = sel1 ? m0_1 : m0_0;
endmodule
