`timescale 1ns/1ps
module mux_tree(output out, input d0, input d1, input d2, input d3, input sel0, input sel1);
  wire sel0_n, sel1_n;
  not g_inv_sel0(sel0_n, sel0);
  not g_inv_sel1(sel1_n, sel1);

  // Level 0 mux 0: m0_0 = sel0 ? d1 : d0
  wire m0_0, m0_0_t0, m0_0_t1;
  and g_m0_0_a0(m0_0_t0, d0, sel0_n);
  and g_m0_0_a1(m0_0_t1, d1, sel0);
  or  g_m0_0_or(m0_0, m0_0_t0, m0_0_t1);

  // Level 0 mux 1: m0_1 = sel0 ? d3 : d2
  wire m0_1, m0_1_t0, m0_1_t1;
  and g_m0_1_a0(m0_1_t0, d2, sel0_n);
  and g_m0_1_a1(m0_1_t1, d3, sel0);
  or  g_m0_1_or(m0_1, m0_1_t0, m0_1_t1);

  // Level 1: out = sel1 ? m0_1 : m0_0
  wire out_t0, out_t1;
  and g_out_a0(out_t0, m0_0, sel1_n);
  and g_out_a1(out_t1, m0_1, sel1);
  or  g_out_or(out, out_t0, out_t1);
endmodule
