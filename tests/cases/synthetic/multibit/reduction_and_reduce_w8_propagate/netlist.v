`timescale 1ns/1ps
module reduction_dut (
    input  [7:0] bus,
    output reduced_out
);
  // reduced_out = &bus (reduction AND)
  wire t0, t1, t2, t3, t4, t5;
  and g_a0(t0, bus[0], bus[1]);
  and g_a1(t1, t0, bus[2]);
  and g_a2(t2, t1, bus[3]);
  and g_a3(t3, t2, bus[4]);
  and g_a4(t4, t3, bus[5]);
  and g_a5(t5, t4, bus[6]);
  and g_a6(reduced_out, t5, bus[7]);
endmodule
