`timescale 1ns/1ps
module reduction_dut (
    input  [7:0] bus,
    output reduced_out
);
  // reduced_out = |bus (reduction OR)
  wire t0, t1, t2, t3, t4, t5;
  or g_o0(t0, bus[0], bus[1]);
  or g_o1(t1, t0, bus[2]);
  or g_o2(t2, t1, bus[3]);
  or g_o3(t3, t2, bus[4]);
  or g_o4(t4, t3, bus[5]);
  or g_o5(t5, t4, bus[6]);
  or g_o6(reduced_out, t5, bus[7]);
endmodule
