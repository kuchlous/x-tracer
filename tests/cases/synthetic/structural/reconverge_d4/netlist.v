`timescale 1ns/1ps
module reconverge(output out, input src);
  wire a0;
  wire a1;
  wire a2;
  wire a3;
  wire b0;
  wire b1;
  wire b2;
  wire b3;
  buf ga0(a0, src);
  buf ga1(a1, a0);
  buf ga2(a2, a1);
  buf ga3(a3, a2);
  buf gb0(b0, src);
  buf gb1(b1, b0);
  buf gb2(b2, b1);
  buf gb3(b3, b2);
  and merge_gate(out, a3, b3);
endmodule
