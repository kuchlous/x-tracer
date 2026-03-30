// =============================================================================
// Stress Edge Test 4: Tri-State Bus with Multiple Drivers
//
// 4 drivers on a shared bus, each gated by bufif1 (drive when enable=1).
// Only one driver enabled at a time (one-hot select). When driver 2's
// data source is forced to X, the bus carries X when driver 2 is selected.
//
// Tests: multi-driver (tri-state) bus tracing, resolving which driver
// contributed the X value.
// =============================================================================

`timescale 1ns/1ps

module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

module tristate_bus_net (
  input        clk,
  input        rst_n,
  input  [3:0] drv_data,    // data for each driver
  input  [3:0] drv_en,      // one-hot enable for each driver
  output       final_out
);

  // Each driver has a source FF and a bufif1 driving the shared bus
  wire d0_q, d1_q, d2_q, d3_q;

  dff_r ff_d0 (.CLK(clk), .D(drv_data[0]), .RST_N(rst_n), .Q(d0_q));
  dff_r ff_d1 (.CLK(clk), .D(drv_data[1]), .RST_N(rst_n), .Q(d1_q));
  dff_r ff_d2 (.CLK(clk), .D(drv_data[2]), .RST_N(rst_n), .Q(d2_q));
  dff_r ff_d3 (.CLK(clk), .D(drv_data[3]), .RST_N(rst_n), .Q(d3_q));

  // Shared tri-state bus
  wire bus;

  bufif1 tri_d0 (bus, d0_q, drv_en[0]);
  bufif1 tri_d1 (bus, d1_q, drv_en[1]);
  bufif1 tri_d2 (bus, d2_q, drv_en[2]);
  bufif1 tri_d3 (bus, d3_q, drv_en[3]);

  // Bus receiver FF
  wire recv_q;
  dff_r ff_recv (.CLK(clk), .D(bus), .RST_N(rst_n), .Q(recv_q));

  // Output buffer
  wire out_buf;
  buf buf_out (out_buf, recv_q);

  // Output FF
  wire out_q;
  dff_r ff_out (.CLK(clk), .D(out_buf), .RST_N(rst_n), .Q(out_q));

  assign final_out = out_q;

endmodule
