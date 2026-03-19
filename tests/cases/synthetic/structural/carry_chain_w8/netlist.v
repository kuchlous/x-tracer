`timescale 1ns/1ps
module carry_chain(output [7:0] sum, output cout,
                   input [7:0] a, input [7:0] b,
                   input cin);
  wire [8:0] c;
  assign c[0] = cin;
  wire s0;
  assign s0 = a[0] ^ b[0] ^ c[0];
  assign sum[0] = s0;
  assign c[1] = (a[0] & b[0]) | (a[0] & c[0]) | (b[0] & c[0]);
  wire s1;
  assign s1 = a[1] ^ b[1] ^ c[1];
  assign sum[1] = s1;
  assign c[2] = (a[1] & b[1]) | (a[1] & c[1]) | (b[1] & c[1]);
  wire s2;
  assign s2 = a[2] ^ b[2] ^ c[2];
  assign sum[2] = s2;
  assign c[3] = (a[2] & b[2]) | (a[2] & c[2]) | (b[2] & c[2]);
  wire s3;
  assign s3 = a[3] ^ b[3] ^ c[3];
  assign sum[3] = s3;
  assign c[4] = (a[3] & b[3]) | (a[3] & c[3]) | (b[3] & c[3]);
  wire s4;
  assign s4 = a[4] ^ b[4] ^ c[4];
  assign sum[4] = s4;
  assign c[5] = (a[4] & b[4]) | (a[4] & c[4]) | (b[4] & c[4]);
  wire s5;
  assign s5 = a[5] ^ b[5] ^ c[5];
  assign sum[5] = s5;
  assign c[6] = (a[5] & b[5]) | (a[5] & c[5]) | (b[5] & c[5]);
  wire s6;
  assign s6 = a[6] ^ b[6] ^ c[6];
  assign sum[6] = s6;
  assign c[7] = (a[6] & b[6]) | (a[6] & c[6]) | (b[6] & c[6]);
  wire s7;
  assign s7 = a[7] ^ b[7] ^ c[7];
  assign sum[7] = s7;
  assign c[8] = (a[7] & b[7]) | (a[7] & c[7]) | (b[7] & c[7]);
  assign cout = c[8];
endmodule
