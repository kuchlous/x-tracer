`timescale 1ns/1ps
module reduction_dut (
    input  [7:0] bus,
    output reduced_out
);
  // reduced_out = ^bus (reduction XOR)
  wire t0, t1, t2, t3, t4, t5;
  xor g_x0(t0, bus[0], bus[1]);
  xor g_x1(t1, t0, bus[2]);
  xor g_x2(t2, t1, bus[3]);
  xor g_x3(t3, t2, bus[4]);
  xor g_x4(t4, t3, bus[5]);
  xor g_x5(t5, t4, bus[6]);
  xor g_x6(reduced_out, t5, bus[7]);
endmodule
