`timescale 1ns/1ps
module carry_chain(output [15:0] sum, output cout,
                   input [15:0] a, input [15:0] b,
                   input cin);
  wire [16:0] c;
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

  // Bit 8
  wire s8, t8_xor1, t8_ab, t8_ac, t8_bc;
  xor g8_xor1(t8_xor1, a[8], b[8]);
  xor g8_xor2(s8, t8_xor1, c[8]);
  buf g8_sum(sum[8], s8);
  and g8_a1(t8_ab, a[8], b[8]);
  and g8_a2(t8_ac, a[8], c[8]);
  and g8_a3(t8_bc, b[8], c[8]);
  or  g8_or(c[9], t8_ab, t8_ac, t8_bc);

  // Bit 9
  wire s9, t9_xor1, t9_ab, t9_ac, t9_bc;
  xor g9_xor1(t9_xor1, a[9], b[9]);
  xor g9_xor2(s9, t9_xor1, c[9]);
  buf g9_sum(sum[9], s9);
  and g9_a1(t9_ab, a[9], b[9]);
  and g9_a2(t9_ac, a[9], c[9]);
  and g9_a3(t9_bc, b[9], c[9]);
  or  g9_or(c[10], t9_ab, t9_ac, t9_bc);

  // Bit 10
  wire s10, t10_xor1, t10_ab, t10_ac, t10_bc;
  xor g10_xor1(t10_xor1, a[10], b[10]);
  xor g10_xor2(s10, t10_xor1, c[10]);
  buf g10_sum(sum[10], s10);
  and g10_a1(t10_ab, a[10], b[10]);
  and g10_a2(t10_ac, a[10], c[10]);
  and g10_a3(t10_bc, b[10], c[10]);
  or  g10_or(c[11], t10_ab, t10_ac, t10_bc);

  // Bit 11
  wire s11, t11_xor1, t11_ab, t11_ac, t11_bc;
  xor g11_xor1(t11_xor1, a[11], b[11]);
  xor g11_xor2(s11, t11_xor1, c[11]);
  buf g11_sum(sum[11], s11);
  and g11_a1(t11_ab, a[11], b[11]);
  and g11_a2(t11_ac, a[11], c[11]);
  and g11_a3(t11_bc, b[11], c[11]);
  or  g11_or(c[12], t11_ab, t11_ac, t11_bc);

  // Bit 12
  wire s12, t12_xor1, t12_ab, t12_ac, t12_bc;
  xor g12_xor1(t12_xor1, a[12], b[12]);
  xor g12_xor2(s12, t12_xor1, c[12]);
  buf g12_sum(sum[12], s12);
  and g12_a1(t12_ab, a[12], b[12]);
  and g12_a2(t12_ac, a[12], c[12]);
  and g12_a3(t12_bc, b[12], c[12]);
  or  g12_or(c[13], t12_ab, t12_ac, t12_bc);

  // Bit 13
  wire s13, t13_xor1, t13_ab, t13_ac, t13_bc;
  xor g13_xor1(t13_xor1, a[13], b[13]);
  xor g13_xor2(s13, t13_xor1, c[13]);
  buf g13_sum(sum[13], s13);
  and g13_a1(t13_ab, a[13], b[13]);
  and g13_a2(t13_ac, a[13], c[13]);
  and g13_a3(t13_bc, b[13], c[13]);
  or  g13_or(c[14], t13_ab, t13_ac, t13_bc);

  // Bit 14
  wire s14, t14_xor1, t14_ab, t14_ac, t14_bc;
  xor g14_xor1(t14_xor1, a[14], b[14]);
  xor g14_xor2(s14, t14_xor1, c[14]);
  buf g14_sum(sum[14], s14);
  and g14_a1(t14_ab, a[14], b[14]);
  and g14_a2(t14_ac, a[14], c[14]);
  and g14_a3(t14_bc, b[14], c[14]);
  or  g14_or(c[15], t14_ab, t14_ac, t14_bc);

  // Bit 15
  wire s15, t15_xor1, t15_ab, t15_ac, t15_bc;
  xor g15_xor1(t15_xor1, a[15], b[15]);
  xor g15_xor2(s15, t15_xor1, c[15]);
  buf g15_sum(sum[15], s15);
  and g15_a1(t15_ab, a[15], b[15]);
  and g15_a2(t15_ac, a[15], c[15]);
  and g15_a3(t15_bc, b[15], c[15]);
  or  g15_or(c[16], t15_ab, t15_ac, t15_bc);

  buf g_cout(cout, c[16]);
endmodule
