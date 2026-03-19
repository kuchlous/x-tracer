`timescale 1ns/1ps
module bus_encoder(output [7:0] out, input in0, input in1, input in2, input in3, input in4, input in5, input in6, input in7);
  wire c0;
  wire c1;
  wire c2;
  wire c3;
  wire c4;
  wire c5;
  wire c6;
  wire c7;
  buf gb0(c0, in0);
  or g1(c1, in1, c0);
  or g2(c2, in2, c1);
  or g3(c3, in3, c2);
  or g4(c4, in4, c3);
  or g5(c5, in5, c4);
  or g6(c6, in6, c5);
  or g7(c7, in7, c6);
  assign out[0] = c0;
  assign out[1] = c1;
  assign out[2] = c2;
  assign out[3] = c3;
  assign out[4] = c4;
  assign out[5] = c5;
  assign out[6] = c6;
  assign out[7] = c7;
endmodule
