// Tier S1 synthetic: 2-input AND gate
// Case: and_x_masked — a=X, b=0 → y=0 (X masked by 0)
module and2(output y, input a, b);
  and g0(y, a, b);
endmodule
