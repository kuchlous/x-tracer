`timescale 1ns/1ps
module bus_encoder(output [3:0] out, input in0, input in1, input in2, input in3);
  wire c0;
  wire c1;
  wire c2;
  wire c3;
  buf gb0(c0, in0);
  or g1(c1, in1, c0);
  or g2(c2, in2, c1);
  or g3(c3, in3, c2);
  assign out[0] = c0;
  assign out[1] = c1;
  assign out[2] = c2;
  assign out[3] = c3;
endmodule
