// =============================================================================
// Stress Edge Test 2: Wide Fanout Reconvergence
//
// One source signal fans out to 32 parallel paths, each through a different
// gate type (and/or/xor/buf mix), then all 32 paths reconverge through a
// tree of XOR gates to a single output FF.
//
// Tests: single-source identification through massive fanout/reconvergence.
// =============================================================================

`timescale 1ns/1ps

module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

module wide_fanout_net (
  input        clk,
  input        rst_n,
  input        src_in,       // single source signal
  input [31:0] side_in,      // side inputs (non-X, used as second gate input)
  output       final_out
);

  // Stage 1: Source FF captures src_in
  wire src_q;
  dff_r ff_src (.CLK(clk), .D(src_in), .RST_N(rst_n), .Q(src_q));

  // Stage 2: 32 parallel paths from src_q through different gates
  // Each path: gate(src_q, side_in[i]) -> FF
  // side_in values are all 1 so gates propagate X from src_q

  // Path wires: gate outputs and FF outputs
  wire g_0,  g_1,  g_2,  g_3,  g_4,  g_5,  g_6,  g_7;
  wire g_8,  g_9,  g_10, g_11, g_12, g_13, g_14, g_15;
  wire g_16, g_17, g_18, g_19, g_20, g_21, g_22, g_23;
  wire g_24, g_25, g_26, g_27, g_28, g_29, g_30, g_31;

  wire p_0,  p_1,  p_2,  p_3,  p_4,  p_5,  p_6,  p_7;
  wire p_8,  p_9,  p_10, p_11, p_12, p_13, p_14, p_15;
  wire p_16, p_17, p_18, p_19, p_20, p_21, p_22, p_23;
  wire p_24, p_25, p_26, p_27, p_28, p_29, p_30, p_31;

  // Paths 0-7: AND gates (X & 1 = X)
  and and_0  (g_0,  src_q, side_in[0]);
  and and_1  (g_1,  src_q, side_in[1]);
  and and_2  (g_2,  src_q, side_in[2]);
  and and_3  (g_3,  src_q, side_in[3]);
  and and_4  (g_4,  src_q, side_in[4]);
  and and_5  (g_5,  src_q, side_in[5]);
  and and_6  (g_6,  src_q, side_in[6]);
  and and_7  (g_7,  src_q, side_in[7]);

  // Paths 8-15: OR gates (X | 0 = X)
  or or_8   (g_8,  src_q, side_in[8]);
  or or_9   (g_9,  src_q, side_in[9]);
  or or_10  (g_10, src_q, side_in[10]);
  or or_11  (g_11, src_q, side_in[11]);
  or or_12  (g_12, src_q, side_in[12]);
  or or_13  (g_13, src_q, side_in[13]);
  or or_14  (g_14, src_q, side_in[14]);
  or or_15  (g_15, src_q, side_in[15]);

  // Paths 16-23: XOR gates (X ^ anything = X)
  xor xor_16 (g_16, src_q, side_in[16]);
  xor xor_17 (g_17, src_q, side_in[17]);
  xor xor_18 (g_18, src_q, side_in[18]);
  xor xor_19 (g_19, src_q, side_in[19]);
  xor xor_20 (g_20, src_q, side_in[20]);
  xor xor_21 (g_21, src_q, side_in[21]);
  xor xor_22 (g_22, src_q, side_in[22]);
  xor xor_23 (g_23, src_q, side_in[23]);

  // Paths 24-31: BUF gates (just pass through src_q, ignore side_in)
  buf buf_24 (g_24, src_q);
  buf buf_25 (g_25, src_q);
  buf buf_26 (g_26, src_q);
  buf buf_27 (g_27, src_q);
  buf buf_28 (g_28, src_q);
  buf buf_29 (g_29, src_q);
  buf buf_30 (g_30, src_q);
  buf buf_31 (g_31, src_q);

  // Path FFs
  dff_r ff_p0  (.CLK(clk), .D(g_0),  .RST_N(rst_n), .Q(p_0));
  dff_r ff_p1  (.CLK(clk), .D(g_1),  .RST_N(rst_n), .Q(p_1));
  dff_r ff_p2  (.CLK(clk), .D(g_2),  .RST_N(rst_n), .Q(p_2));
  dff_r ff_p3  (.CLK(clk), .D(g_3),  .RST_N(rst_n), .Q(p_3));
  dff_r ff_p4  (.CLK(clk), .D(g_4),  .RST_N(rst_n), .Q(p_4));
  dff_r ff_p5  (.CLK(clk), .D(g_5),  .RST_N(rst_n), .Q(p_5));
  dff_r ff_p6  (.CLK(clk), .D(g_6),  .RST_N(rst_n), .Q(p_6));
  dff_r ff_p7  (.CLK(clk), .D(g_7),  .RST_N(rst_n), .Q(p_7));
  dff_r ff_p8  (.CLK(clk), .D(g_8),  .RST_N(rst_n), .Q(p_8));
  dff_r ff_p9  (.CLK(clk), .D(g_9),  .RST_N(rst_n), .Q(p_9));
  dff_r ff_p10 (.CLK(clk), .D(g_10), .RST_N(rst_n), .Q(p_10));
  dff_r ff_p11 (.CLK(clk), .D(g_11), .RST_N(rst_n), .Q(p_11));
  dff_r ff_p12 (.CLK(clk), .D(g_12), .RST_N(rst_n), .Q(p_12));
  dff_r ff_p13 (.CLK(clk), .D(g_13), .RST_N(rst_n), .Q(p_13));
  dff_r ff_p14 (.CLK(clk), .D(g_14), .RST_N(rst_n), .Q(p_14));
  dff_r ff_p15 (.CLK(clk), .D(g_15), .RST_N(rst_n), .Q(p_15));
  dff_r ff_p16 (.CLK(clk), .D(g_16), .RST_N(rst_n), .Q(p_16));
  dff_r ff_p17 (.CLK(clk), .D(g_17), .RST_N(rst_n), .Q(p_17));
  dff_r ff_p18 (.CLK(clk), .D(g_18), .RST_N(rst_n), .Q(p_18));
  dff_r ff_p19 (.CLK(clk), .D(g_19), .RST_N(rst_n), .Q(p_19));
  dff_r ff_p20 (.CLK(clk), .D(g_20), .RST_N(rst_n), .Q(p_20));
  dff_r ff_p21 (.CLK(clk), .D(g_21), .RST_N(rst_n), .Q(p_21));
  dff_r ff_p22 (.CLK(clk), .D(g_22), .RST_N(rst_n), .Q(p_22));
  dff_r ff_p23 (.CLK(clk), .D(g_23), .RST_N(rst_n), .Q(p_23));
  dff_r ff_p24 (.CLK(clk), .D(g_24), .RST_N(rst_n), .Q(p_24));
  dff_r ff_p25 (.CLK(clk), .D(g_25), .RST_N(rst_n), .Q(p_25));
  dff_r ff_p26 (.CLK(clk), .D(g_26), .RST_N(rst_n), .Q(p_26));
  dff_r ff_p27 (.CLK(clk), .D(g_27), .RST_N(rst_n), .Q(p_27));
  dff_r ff_p28 (.CLK(clk), .D(g_28), .RST_N(rst_n), .Q(p_28));
  dff_r ff_p29 (.CLK(clk), .D(g_29), .RST_N(rst_n), .Q(p_29));
  dff_r ff_p30 (.CLK(clk), .D(g_30), .RST_N(rst_n), .Q(p_30));
  dff_r ff_p31 (.CLK(clk), .D(g_31), .RST_N(rst_n), .Q(p_31));

  // Stage 3: Reconvergence tree -- 5 levels of XOR reduction (32->16->8->4->2->1)
  // Level 1: 16 XOR gates
  wire t1_0, t1_1, t1_2, t1_3, t1_4, t1_5, t1_6, t1_7;
  wire t1_8, t1_9, t1_10, t1_11, t1_12, t1_13, t1_14, t1_15;
  xor xr1_0  (t1_0,  p_0,  p_1);
  xor xr1_1  (t1_1,  p_2,  p_3);
  xor xr1_2  (t1_2,  p_4,  p_5);
  xor xr1_3  (t1_3,  p_6,  p_7);
  xor xr1_4  (t1_4,  p_8,  p_9);
  xor xr1_5  (t1_5,  p_10, p_11);
  xor xr1_6  (t1_6,  p_12, p_13);
  xor xr1_7  (t1_7,  p_14, p_15);
  xor xr1_8  (t1_8,  p_16, p_17);
  xor xr1_9  (t1_9,  p_18, p_19);
  xor xr1_10 (t1_10, p_20, p_21);
  xor xr1_11 (t1_11, p_22, p_23);
  xor xr1_12 (t1_12, p_24, p_25);
  xor xr1_13 (t1_13, p_26, p_27);
  xor xr1_14 (t1_14, p_28, p_29);
  xor xr1_15 (t1_15, p_30, p_31);

  // Level 2: 8 XOR gates
  wire t2_0, t2_1, t2_2, t2_3, t2_4, t2_5, t2_6, t2_7;
  xor xr2_0 (t2_0, t1_0,  t1_1);
  xor xr2_1 (t2_1, t1_2,  t1_3);
  xor xr2_2 (t2_2, t1_4,  t1_5);
  xor xr2_3 (t2_3, t1_6,  t1_7);
  xor xr2_4 (t2_4, t1_8,  t1_9);
  xor xr2_5 (t2_5, t1_10, t1_11);
  xor xr2_6 (t2_6, t1_12, t1_13);
  xor xr2_7 (t2_7, t1_14, t1_15);

  // Level 3: 4 XOR gates
  wire t3_0, t3_1, t3_2, t3_3;
  xor xr3_0 (t3_0, t2_0, t2_1);
  xor xr3_1 (t3_1, t2_2, t2_3);
  xor xr3_2 (t3_2, t2_4, t2_5);
  xor xr3_3 (t3_3, t2_6, t2_7);

  // Level 4: 2 XOR gates
  wire t4_0, t4_1;
  xor xr4_0 (t4_0, t3_0, t3_1);
  xor xr4_1 (t4_1, t3_2, t3_3);

  // Level 5: final XOR
  wire t5_0;
  xor xr5_0 (t5_0, t4_0, t4_1);

  // Output FF
  wire out_q;
  dff_r ff_out (.CLK(clk), .D(t5_0), .RST_N(rst_n), .Q(out_q));

  assign final_out = out_q;

endmodule
