// =============================================================================
// Stress Edge Test 3: Clock Domain Crossing (CDC)
//
// Two clock domains: clk_a (10ns period) and clk_b (14ns period).
// Domain A has a 3-stage pipeline. Domain B has a 2-FF synchronizer
// followed by a 2-stage pipeline. X injected in domain A stage 0,
// queried at domain B output.
//
// Tests: multi-clock handling, tracing across asynchronous boundaries.
// =============================================================================

`timescale 1ns/1ps

module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

module clock_crossing_net (
  input  clk_a,
  input  clk_b,
  input  rst_n,
  input  data_in,
  output final_out
);

  // ---- Domain A: 3-stage pipeline on clk_a ----
  wire a_q0, a_q1, a_q2;
  wire a_buf0, a_buf1;

  dff_r ff_a0 (.CLK(clk_a), .D(data_in), .RST_N(rst_n), .Q(a_q0));
  buf buf_a0 (a_buf0, a_q0);
  dff_r ff_a1 (.CLK(clk_a), .D(a_buf0),  .RST_N(rst_n), .Q(a_q1));
  buf buf_a1 (a_buf1, a_q1);
  dff_r ff_a2 (.CLK(clk_a), .D(a_buf1),  .RST_N(rst_n), .Q(a_q2));

  // ---- CDC Synchronizer: 2 FFs on clk_b ----
  wire sync_q0, sync_q1;
  wire sync_buf;

  dff_r ff_sync0 (.CLK(clk_b), .D(a_q2),     .RST_N(rst_n), .Q(sync_q0));
  buf buf_sync (sync_buf, sync_q0);
  dff_r ff_sync1 (.CLK(clk_b), .D(sync_buf),  .RST_N(rst_n), .Q(sync_q1));

  // ---- Domain B: 2-stage pipeline on clk_b ----
  wire b_q0, b_q1;
  wire b_buf0;

  dff_r ff_b0 (.CLK(clk_b), .D(sync_q1), .RST_N(rst_n), .Q(b_q0));
  buf buf_b0 (b_buf0, b_q0);
  dff_r ff_b1 (.CLK(clk_b), .D(b_buf0),  .RST_N(rst_n), .Q(b_q1));

  assign final_out = b_q1;

endmodule
