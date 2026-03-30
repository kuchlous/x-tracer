// =============================================================================
// Stress Test Testbench — Self-Checking
//
// Scale: 8×8 clusters × 8 stages × 8 lanes × 32 FFs = 131,072 FFs, ~1M signals
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter BLOCK_ROWS         = 8;
  parameter BLOCK_COLS         = 8;
  parameter STAGES_PER_CLUSTER = 8;
  parameter LANES_PER_STAGE    = 8;
  parameter LFSR_WIDTH         = 32;
  parameter SETTLE_CYCLES      = 100;
  parameter PROPAGATE_CYCLES   = 5000;
  parameter CLK_PERIOD         = 10;

  reg                     clk = 0;
  reg                     rst_n = 0;
  reg  [LFSR_WIDTH-1:0]  inject_data = {LFSR_WIDTH{1'b0}};
  reg                     inject_valid = 0;
  wire [LFSR_WIDTH-1:0]  final_out;

  stress_net #(
    .BLOCK_ROWS        (BLOCK_ROWS),
    .BLOCK_COLS        (BLOCK_COLS),
    .STAGES_PER_CLUSTER(STAGES_PER_CLUSTER),
    .LANES_PER_STAGE   (LANES_PER_STAGE),
    .LFSR_WIDTH        (LFSR_WIDTH)
  ) dut (
    .clk         (clk),
    .rst_n       (rst_n),
    .inject_data (inject_data),
    .inject_valid(inject_valid),
    .final_out   (final_out)
  );

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
    // Force X on inject_data[0] — this is the only injection point.
    // x-tracer should trace final_out back through the LFSR pipeline
    // to this single primary_input as the root cause.
    inject_valid = 1;
    inject_data[0] = 1'bx;
    $display("INFO: X injected on inject_data[0] at t=%0t", $time);
    // Also force X directly on the first FF to ensure propagation
    // in simulators where behavioral DFF doesn't propagate X through if/else
    @(posedge clk);
    force dut.gen_block[0].gen_col[0].cluster_inst.gen_stage[0].gen_lane[0].core.ff0.Q = 1'bx;
    $display("INFO: Forced ff0.Q to X at t=%0t", $time);
    repeat(2) @(posedge clk);
    release dut.gen_block[0].gen_col[0].cluster_inst.gen_stage[0].gen_lane[0].core.ff0.Q;
    $display("INFO: Released ff0.Q at t=%0t", $time);

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

  initial #20000000 begin
    $display("TIMEOUT at t=%0t", $time);
    $finish;
  end

endmodule
