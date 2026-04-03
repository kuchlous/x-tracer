`timescale 1ns/1ps
module carry_chain(output [3:0] sum, output cout,
                   input [3:0] a, input [3:0] b,
                   input cin);
  wire [4:0] c;
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

  buf g_cout(cout, c[4]);
endmodule
