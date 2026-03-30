// =============================================================================
// Stress Edge Test 5: Nested Clock Gating (3 Levels of ICG)
//
// 3 levels of integrated clock gates (ICG cells modeled as AND gates
// gating the clock). X on the innermost enable propagates to all
// downstream FFs by corrupting their clock.
//
// Hierarchy:
//   clk -> ICG_L1(en1) -> gclk_l1
//                           -> ICG_L2(en2) -> gclk_l2
//                                               -> ICG_L3(en3) -> gclk_l3
//                                                                   -> FF_A, FF_B (leaf FFs)
//                                               -> FF_C (uses gclk_l2)
//                           -> FF_D (uses gclk_l1)
//
// X forced on en3 (innermost gate enable). This makes gclk_l3 = X,
// which corrupts FF_A and FF_B outputs.
//
// Tests: clock-X propagation through nested gating hierarchy.
// =============================================================================

`timescale 1ns/1ps

module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

// ICG cell: latch-based clock gate (behavioral for simulation)
// When EN is sampled high at negedge clk, gate opens on next posedge.
// Modeled simply as AND for gate-level X propagation testing.
module icg_cell(input CLK, input EN, output GCLK);
  reg en_lat;
  initial en_lat = 1'b0;
  always @(CLK or EN)
    if (!CLK) en_lat = EN;   // transparent when CLK low (latch)
  and and_gate (GCLK, CLK, en_lat);
endmodule

module nested_clock_gate_net (
  input  clk,
  input  rst_n,
  input  en1,         // level 1 clock gate enable
  input  en2,         // level 2 clock gate enable
  input  en3,         // level 3 clock gate enable (innermost)
  input  data_a,
  input  data_b,
  input  data_c,
  input  data_d,
  output out_a,
  output out_b,
  output out_c,
  output out_d,
  output final_out    // combined output
);

  // Level 1 ICG: clk gated by en1
  wire gclk_l1;
  icg_cell icg_l1 (.CLK(clk), .EN(en1), .GCLK(gclk_l1));

  // Level 2 ICG: gclk_l1 gated by en2
  wire gclk_l2;
  icg_cell icg_l2 (.CLK(gclk_l1), .EN(en2), .GCLK(gclk_l2));

  // Level 3 ICG: gclk_l2 gated by en3 (innermost)
  wire gclk_l3;
  icg_cell icg_l3 (.CLK(gclk_l2), .EN(en3), .GCLK(gclk_l3));

  // Leaf FFs on gclk_l3 (affected by en3 X)
  wire qa, qb;
  dff_r ff_a (.CLK(gclk_l3), .D(data_a), .RST_N(rst_n), .Q(qa));
  dff_r ff_b (.CLK(gclk_l3), .D(data_b), .RST_N(rst_n), .Q(qb));

  // FF on gclk_l2 (should NOT be affected by en3 X directly)
  wire qc;
  dff_r ff_c (.CLK(gclk_l2), .D(data_c), .RST_N(rst_n), .Q(qc));

  // FF on gclk_l1 (should NOT be affected by en3 X directly)
  wire qd;
  dff_r ff_d (.CLK(gclk_l1), .D(data_d), .RST_N(rst_n), .Q(qd));

  // Output assignments
  assign out_a = qa;
  assign out_b = qb;
  assign out_c = qc;
  assign out_d = qd;

  // Combined output: XOR of all leaf FF outputs
  wire xor_ab, xor_cd;
  xor xor_g1 (xor_ab, qa, qb);
  xor xor_g2 (xor_cd, qc, qd);
  xor xor_g3 (final_out, xor_ab, xor_cd);

endmodule
