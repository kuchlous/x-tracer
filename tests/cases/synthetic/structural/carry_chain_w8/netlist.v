`timescale 1ns/1ps
module carry_chain(output [7:0] sum, output cout,
                   input [7:0] a, input [7:0] b,
                   input cin);
  wire [8:0] c;
  buf g_cin(c[0], cin);

  // Bit 0
  wire s0, t0_xor1, t0_ab, t0_ac, t0_bc;
  xor g0_xor1(t0_xor1, a[0], b[0]);
  xor g0_xor2(s0, t0_xor1, c[0]);
  buf g0_sum(sum[0], s0);
  and g0_a1(t0_ab, a[0], b[0]);
  and g0_a2(t0_ac, a[0], c[0]);
  and g0_a3(t0_bc, b[0], c[0]);
  or  g0_or(c[1], t0_ab, t0_ac, t0_bc);

  // Bit 1
  wire s1, t1_xor1, t1_ab, t1_ac, t1_bc;
  xor g1_xor1(t1_xor1, a[1], b[1]);
  xor g1_xor2(s1, t1_xor1, c[1]);
  buf g1_sum(sum[1], s1);
  and g1_a1(t1_ab, a[1], b[1]);
  and g1_a2(t1_ac, a[1], c[1]);
  and g1_a3(t1_bc, b[1], c[1]);
  or  g1_or(c[2], t1_ab, t1_ac, t1_bc);

  // Bit 2
  wire s2, t2_xor1, t2_ab, t2_ac, t2_bc;
  xor g2_xor1(t2_xor1, a[2], b[2]);
  xor g2_xor2(s2, t2_xor1, c[2]);
  buf g2_sum(sum[2], s2);
  and g2_a1(t2_ab, a[2], b[2]);
  and g2_a2(t2_ac, a[2], c[2]);
  and g2_a3(t2_bc, b[2], c[2]);
  or  g2_or(c[3], t2_ab, t2_ac, t2_bc);

  // Bit 3
  wire s3, t3_xor1, t3_ab, t3_ac, t3_bc;
  xor g3_xor1(t3_xor1, a[3], b[3]);
  xor g3_xor2(s3, t3_xor1, c[3]);
  buf g3_sum(sum[3], s3);
  and g3_a1(t3_ab, a[3], b[3]);
  and g3_a2(t3_ac, a[3], c[3]);
  and g3_a3(t3_bc, b[3], c[3]);
  or  g3_or(c[4], t3_ab, t3_ac, t3_bc);

  // Bit 4
  wire s4, t4_xor1, t4_ab, t4_ac, t4_bc;
  xor g4_xor1(t4_xor1, a[4], b[4]);
  xor g4_xor2(s4, t4_xor1, c[4]);
  buf g4_sum(sum[4], s4);
  and g4_a1(t4_ab, a[4], b[4]);
  and g4_a2(t4_ac, a[4], c[4]);
  and g4_a3(t4_bc, b[4], c[4]);
  or  g4_or(c[5], t4_ab, t4_ac, t4_bc);

  // Bit 5
  wire s5, t5_xor1, t5_ab, t5_ac, t5_bc;
  xor g5_xor1(t5_xor1, a[5], b[5]);
  xor g5_xor2(s5, t5_xor1, c[5]);
  buf g5_sum(sum[5], s5);
  and g5_a1(t5_ab, a[5], b[5]);
  and g5_a2(t5_ac, a[5], c[5]);
  and g5_a3(t5_bc, b[5], c[5]);
  or  g5_or(c[6], t5_ab, t5_ac, t5_bc);

  // Bit 6
  wire s6, t6_xor1, t6_ab, t6_ac, t6_bc;
  xor g6_xor1(t6_xor1, a[6], b[6]);
  xor g6_xor2(s6, t6_xor1, c[6]);
  buf g6_sum(sum[6], s6);
  and g6_a1(t6_ab, a[6], b[6]);
  and g6_a2(t6_ac, a[6], c[6]);
  and g6_a3(t6_bc, b[6], c[6]);
  or  g6_or(c[7], t6_ab, t6_ac, t6_bc);

  // Bit 7
  wire s7, t7_xor1, t7_ab, t7_ac, t7_bc;
  xor g7_xor1(t7_xor1, a[7], b[7]);
  xor g7_xor2(s7, t7_xor1, c[7]);
  buf g7_sum(sum[7], s7);
  and g7_a1(t7_ab, a[7], b[7]);
  and g7_a2(t7_ac, a[7], c[7]);
  and g7_a3(t7_bc, b[7], c[7]);
  or  g7_or(c[8], t7_ab, t7_ac, t7_bc);

  buf g_cout(cout, c[8]);
endmodule
