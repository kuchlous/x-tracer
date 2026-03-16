`timescale 1ns/1ps
module reconverge(output y, input a);
  wire w1, w2;
  not g0(w1, a);
  buf g1(w2, a);
  and g2(y, w1, w2);
endmodule
