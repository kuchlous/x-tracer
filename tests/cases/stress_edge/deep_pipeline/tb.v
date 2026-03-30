// =============================================================================
// Stress Edge Test 1: Deep Pipeline -- Testbench
//
// 104-stage FF chain. X forced at ff_0.Q, queried at final_out after
// 104+ clock cycles of propagation.
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter CLK_PERIOD       = 10;
  parameter SETTLE_CYCLES    = 20;
  parameter PROPAGATE_CYCLES = 120;  // >104 stages

  reg  clk   = 0;
  reg  rst_n = 0;
  reg  data_in = 0;
  wire final_out;

  deep_pipeline_net dut (
    .clk(clk), .rst_n(rst_n), .data_in(data_in), .final_out(final_out)
  );

  always #(CLK_PERIOD/2) clk = ~clk;

  initial begin
    $dumpfile("sim.vcd");
    $dumpvars(0, tb);
  end

  reg has_x_before;
  reg test_pass;

  initial begin
    // Phase 1: Reset
    rst_n = 0;
    data_in = 0;
    #80;

    // Phase 2: Release reset, let pipeline settle to 0
    rst_n = 1;
    data_in = 1'b1;
    repeat (SETTLE_CYCLES) @(posedge clk);

    // Verify clean state at output
    has_x_before = (final_out === 1'bx);
    if (has_x_before) begin
      $display("FAIL: final_out has X before injection at t=%0t", $time);
      $finish;
    end
    $display("INFO: Clean at t=%0t, final_out=%b", $time, final_out);

    // Phase 3: Inject X at stage 0 FF output
    @(posedge clk);
    force dut.ff_0.Q = 1'bx;
    $display("INFO: Forced ff_0.Q to X at t=%0t", $time);
    repeat(2) @(posedge clk);
    release dut.ff_0.Q;
    $display("INFO: Released ff_0.Q at t=%0t", $time);

    // Phase 4: Wait for X to propagate through all 104 stages
    repeat (PROPAGATE_CYCLES) @(posedge clk);

    // Phase 5: Self-check
    test_pass = (final_out === 1'bx);
    if (test_pass)
      $display("PASS: final_out has X at t=%0t, val=%b", $time, final_out);
    else
      $display("FAIL: no X in final_out at t=%0t, val=%b", $time, final_out);

    repeat (5) @(posedge clk);
    $finish;
  end

  initial #5000000 begin
    $display("TIMEOUT at t=%0t", $time);
    $finish;
  end

endmodule
