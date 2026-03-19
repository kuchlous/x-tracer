`timescale 1ns/1ps
module mux_tree(output out, input d0, input d1, input d2, input d3, input d4, input d5, input d6, input d7, input sel0, input sel1, input sel2);
  wire m0_0;
  assign m0_0 = sel0 ? d1 : d0;
  wire m0_1;
  assign m0_1 = sel0 ? d3 : d2;
  wire m0_2;
  assign m0_2 = sel0 ? d5 : d4;
  wire m0_3;
  assign m0_3 = sel0 ? d7 : d6;
  wire m1_0;
  assign m1_0 = sel1 ? m0_1 : m0_0;
  wire m1_1;
  assign m1_1 = sel1 ? m0_3 : m0_2;
  assign out = sel2 ? m1_1 : m1_0;
endmodule
