`timescale 1ns/1ps
module reconverge(output out, input src);
  wire a0;
  wire a1;
  wire b0;
  wire b1;
  buf ga0(a0, src);
  buf ga1(a1, a0);
  buf gb0(b0, src);
  buf gb1(b1, b0);
  and merge_gate(out, a1, b1);
endmodule
