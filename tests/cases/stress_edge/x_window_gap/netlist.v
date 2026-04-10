// =============================================================================
// Stress Edge Test: X Window Gap
//
// DFF with D driven by a mux selecting between two sources (src_a, src_b).
// Testbench makes D go X (from src_a) -> known -> X (from src_b), then a
// clock edge captures the second X.  Tests that the temporal skip traces to
// the CURRENT X window's root cause (src_b), not the first-ever X (src_a).
// =============================================================================

`timescale 1ns/1ps

// DFF with async active-low reset
module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

module x_window_gap_net (
  input  clk,
  input  rst_n,
  input  src_a,
  input  src_b,
  input  sel,
  output final_out
);

  // MUX: sel=0 -> src_a, sel=1 -> src_b
  wire mux_sel_inv, mux_a_arm, mux_b_arm, mux_out;
  not  g_inv(mux_sel_inv, sel);
  and  g_a(mux_a_arm, src_a, mux_sel_inv);
  and  g_b(mux_b_arm, src_b, sel);
  or   g_mux(mux_out, mux_a_arm, mux_b_arm);

  // DFF captures mux output
  wire ff_q;
  dff_r ff0(.CLK(clk), .D(mux_out), .RST_N(rst_n), .Q(ff_q));

  // Output buffer
  buf g_out(final_out, ff_q);

endmodule
