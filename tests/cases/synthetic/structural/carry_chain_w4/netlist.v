`timescale 1ns/1ps
module carry_chain(output [3:0] sum, output cout,
                   input [3:0] a, input [3:0] b,
                   input cin);
  wire [4:0] c;
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
  assign cout = c[4];
endmodule
