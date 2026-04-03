`timescale 1ns/1ps
module carry_chain(output [31:0] sum, output cout,
                   input [31:0] a, input [31:0] b,
                   input cin);
  wire [32:0] c;
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

  // Bit 16
  wire s16, t16_xor1, t16_ab, t16_ac, t16_bc;
  xor g16_xor1(t16_xor1, a[16], b[16]);
  xor g16_xor2(s16, t16_xor1, c[16]);
  buf g16_sum(sum[16], s16);
  and g16_a1(t16_ab, a[16], b[16]);
  and g16_a2(t16_ac, a[16], c[16]);
  and g16_a3(t16_bc, b[16], c[16]);
  or  g16_or(c[17], t16_ab, t16_ac, t16_bc);

  // Bit 17
  wire s17, t17_xor1, t17_ab, t17_ac, t17_bc;
  xor g17_xor1(t17_xor1, a[17], b[17]);
  xor g17_xor2(s17, t17_xor1, c[17]);
  buf g17_sum(sum[17], s17);
  and g17_a1(t17_ab, a[17], b[17]);
  and g17_a2(t17_ac, a[17], c[17]);
  and g17_a3(t17_bc, b[17], c[17]);
  or  g17_or(c[18], t17_ab, t17_ac, t17_bc);

  // Bit 18
  wire s18, t18_xor1, t18_ab, t18_ac, t18_bc;
  xor g18_xor1(t18_xor1, a[18], b[18]);
  xor g18_xor2(s18, t18_xor1, c[18]);
  buf g18_sum(sum[18], s18);
  and g18_a1(t18_ab, a[18], b[18]);
  and g18_a2(t18_ac, a[18], c[18]);
  and g18_a3(t18_bc, b[18], c[18]);
  or  g18_or(c[19], t18_ab, t18_ac, t18_bc);

  // Bit 19
  wire s19, t19_xor1, t19_ab, t19_ac, t19_bc;
  xor g19_xor1(t19_xor1, a[19], b[19]);
  xor g19_xor2(s19, t19_xor1, c[19]);
  buf g19_sum(sum[19], s19);
  and g19_a1(t19_ab, a[19], b[19]);
  and g19_a2(t19_ac, a[19], c[19]);
  and g19_a3(t19_bc, b[19], c[19]);
  or  g19_or(c[20], t19_ab, t19_ac, t19_bc);

  // Bit 20
  wire s20, t20_xor1, t20_ab, t20_ac, t20_bc;
  xor g20_xor1(t20_xor1, a[20], b[20]);
  xor g20_xor2(s20, t20_xor1, c[20]);
  buf g20_sum(sum[20], s20);
  and g20_a1(t20_ab, a[20], b[20]);
  and g20_a2(t20_ac, a[20], c[20]);
  and g20_a3(t20_bc, b[20], c[20]);
  or  g20_or(c[21], t20_ab, t20_ac, t20_bc);

  // Bit 21
  wire s21, t21_xor1, t21_ab, t21_ac, t21_bc;
  xor g21_xor1(t21_xor1, a[21], b[21]);
  xor g21_xor2(s21, t21_xor1, c[21]);
  buf g21_sum(sum[21], s21);
  and g21_a1(t21_ab, a[21], b[21]);
  and g21_a2(t21_ac, a[21], c[21]);
  and g21_a3(t21_bc, b[21], c[21]);
  or  g21_or(c[22], t21_ab, t21_ac, t21_bc);

  // Bit 22
  wire s22, t22_xor1, t22_ab, t22_ac, t22_bc;
  xor g22_xor1(t22_xor1, a[22], b[22]);
  xor g22_xor2(s22, t22_xor1, c[22]);
  buf g22_sum(sum[22], s22);
  and g22_a1(t22_ab, a[22], b[22]);
  and g22_a2(t22_ac, a[22], c[22]);
  and g22_a3(t22_bc, b[22], c[22]);
  or  g22_or(c[23], t22_ab, t22_ac, t22_bc);

  // Bit 23
  wire s23, t23_xor1, t23_ab, t23_ac, t23_bc;
  xor g23_xor1(t23_xor1, a[23], b[23]);
  xor g23_xor2(s23, t23_xor1, c[23]);
  buf g23_sum(sum[23], s23);
  and g23_a1(t23_ab, a[23], b[23]);
  and g23_a2(t23_ac, a[23], c[23]);
  and g23_a3(t23_bc, b[23], c[23]);
  or  g23_or(c[24], t23_ab, t23_ac, t23_bc);

  // Bit 24
  wire s24, t24_xor1, t24_ab, t24_ac, t24_bc;
  xor g24_xor1(t24_xor1, a[24], b[24]);
  xor g24_xor2(s24, t24_xor1, c[24]);
  buf g24_sum(sum[24], s24);
  and g24_a1(t24_ab, a[24], b[24]);
  and g24_a2(t24_ac, a[24], c[24]);
  and g24_a3(t24_bc, b[24], c[24]);
  or  g24_or(c[25], t24_ab, t24_ac, t24_bc);

  // Bit 25
  wire s25, t25_xor1, t25_ab, t25_ac, t25_bc;
  xor g25_xor1(t25_xor1, a[25], b[25]);
  xor g25_xor2(s25, t25_xor1, c[25]);
  buf g25_sum(sum[25], s25);
  and g25_a1(t25_ab, a[25], b[25]);
  and g25_a2(t25_ac, a[25], c[25]);
  and g25_a3(t25_bc, b[25], c[25]);
  or  g25_or(c[26], t25_ab, t25_ac, t25_bc);

  // Bit 26
  wire s26, t26_xor1, t26_ab, t26_ac, t26_bc;
  xor g26_xor1(t26_xor1, a[26], b[26]);
  xor g26_xor2(s26, t26_xor1, c[26]);
  buf g26_sum(sum[26], s26);
  and g26_a1(t26_ab, a[26], b[26]);
  and g26_a2(t26_ac, a[26], c[26]);
  and g26_a3(t26_bc, b[26], c[26]);
  or  g26_or(c[27], t26_ab, t26_ac, t26_bc);

  // Bit 27
  wire s27, t27_xor1, t27_ab, t27_ac, t27_bc;
  xor g27_xor1(t27_xor1, a[27], b[27]);
  xor g27_xor2(s27, t27_xor1, c[27]);
  buf g27_sum(sum[27], s27);
  and g27_a1(t27_ab, a[27], b[27]);
  and g27_a2(t27_ac, a[27], c[27]);
  and g27_a3(t27_bc, b[27], c[27]);
  or  g27_or(c[28], t27_ab, t27_ac, t27_bc);

  // Bit 28
  wire s28, t28_xor1, t28_ab, t28_ac, t28_bc;
  xor g28_xor1(t28_xor1, a[28], b[28]);
  xor g28_xor2(s28, t28_xor1, c[28]);
  buf g28_sum(sum[28], s28);
  and g28_a1(t28_ab, a[28], b[28]);
  and g28_a2(t28_ac, a[28], c[28]);
  and g28_a3(t28_bc, b[28], c[28]);
  or  g28_or(c[29], t28_ab, t28_ac, t28_bc);

  // Bit 29
  wire s29, t29_xor1, t29_ab, t29_ac, t29_bc;
  xor g29_xor1(t29_xor1, a[29], b[29]);
  xor g29_xor2(s29, t29_xor1, c[29]);
  buf g29_sum(sum[29], s29);
  and g29_a1(t29_ab, a[29], b[29]);
  and g29_a2(t29_ac, a[29], c[29]);
  and g29_a3(t29_bc, b[29], c[29]);
  or  g29_or(c[30], t29_ab, t29_ac, t29_bc);

  // Bit 30
  wire s30, t30_xor1, t30_ab, t30_ac, t30_bc;
  xor g30_xor1(t30_xor1, a[30], b[30]);
  xor g30_xor2(s30, t30_xor1, c[30]);
  buf g30_sum(sum[30], s30);
  and g30_a1(t30_ab, a[30], b[30]);
  and g30_a2(t30_ac, a[30], c[30]);
  and g30_a3(t30_bc, b[30], c[30]);
  or  g30_or(c[31], t30_ab, t30_ac, t30_bc);

  // Bit 31
  wire s31, t31_xor1, t31_ab, t31_ac, t31_bc;
  xor g31_xor1(t31_xor1, a[31], b[31]);
  xor g31_xor2(s31, t31_xor1, c[31]);
  buf g31_sum(sum[31], s31);
  and g31_a1(t31_ab, a[31], b[31]);
  and g31_a2(t31_ac, a[31], c[31]);
  and g31_a3(t31_bc, b[31], c[31]);
  or  g31_or(c[32], t31_ab, t31_ac, t31_bc);

  buf g_cout(cout, c[32]);
endmodule
