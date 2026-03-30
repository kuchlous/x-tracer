// =============================================================================
// Stress Test Testbench -- Self-Checking
//
// Scale: 2x2 clusters x 2 stages x 2 lanes x 8 FFs = 128 DFFs
// Fully flattened netlist, no 2D arrays.
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter LFSR_WIDTH         = 8;
  parameter SETTLE_CYCLES      = 100;
  parameter PROPAGATE_CYCLES   = 100;
  parameter CLK_PERIOD         = 10;

  reg                     clk = 0;
  reg                     rst_n = 0;
  reg  [LFSR_WIDTH-1:0]  inject_data = {LFSR_WIDTH{1'b0}};
  reg                     inject_valid = 0;
  wire [LFSR_WIDTH-1:0]  final_out;

  stress_net dut (.clk(clk), .rst_n(rst_n), .inject_data(inject_data), .inject_valid(inject_valid), .final_out(final_out));

  always #(CLK_PERIOD/2) clk = ~clk;

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  integer i;
  reg test_pass;
  reg has_x_before;

  initial begin
    // Phase 1: Reset
    rst_n = 0;
    inject_valid = 0;
    inject_data = 0;
    #80;

    // Phase 2: Release reset, settle
    rst_n = 1;
    repeat (SETTLE_CYCLES) @(posedge clk);

    // Verify clean state
    has_x_before = 0;
    for (i = 0; i < LFSR_WIDTH; i = i + 1)
      if (final_out[i] === 1'bx) has_x_before = 1;
    if (has_x_before) begin
      $display("FAIL: final_out has X before injection at t=%0t", $time);
      $finish;
    end
    $display("INFO: Clean at t=%0t, final_out=%h", $time, final_out);

    // Phase 3: Inject X on a single primary input
    inject_valid = 1;
    inject_data[0] = 1'bx;
    $display("INFO: X injected on inject_data[0] at t=%0t", $time);
    // Force X directly on the first FF to ensure propagation
    @(posedge clk);
    force dut.r0c0_s0l0_ff0.Q = 1'bx;
    $display("INFO: Forced r0c0_s0l0_ff0.Q to X at t=%0t", $time);
    repeat(2) @(posedge clk);
    release dut.r0c0_s0l0_ff0.Q;
    $display("INFO: Released r0c0_s0l0_ff0.Q at t=%0t", $time);

    // Phase 4: Propagate
    repeat (PROPAGATE_CYCLES) @(posedge clk);

    // Phase 5: Self-check
    test_pass = 0;
    for (i = 0; i < LFSR_WIDTH; i = i + 1)
      if (final_out[i] === 1'bx) test_pass = 1;

    if (test_pass)
      $display("PASS: final_out has X at t=%0t, val=%b", $time, final_out);
    else
      $display("FAIL: no X in final_out at t=%0t, val=%b", $time, final_out);

    repeat (10) @(posedge clk);
    $finish;
  end

  initial #2000000 begin
    $display("TIMEOUT at t=%0t", $time);
    $finish;
  end

endmodule
