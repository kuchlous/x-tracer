// =============================================================================
// Stress Edge Test 3: Clock Domain Crossing -- Testbench
//
// Two asynchronous clocks. X injected in domain A, queried in domain B.
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter CLKA_PERIOD = 10;  // 100 MHz
  parameter CLKB_PERIOD = 14;  // ~71 MHz (incommensurate)

  reg  clk_a  = 0;
  reg  clk_b  = 0;
  reg  rst_n  = 0;
  reg  data_in = 0;
  wire final_out;

  clock_crossing_net dut (
    .clk_a(clk_a), .clk_b(clk_b),
    .rst_n(rst_n), .data_in(data_in),
    .final_out(final_out)
  );

  always #(CLKA_PERIOD/2) clk_a = ~clk_a;
  always #(CLKB_PERIOD/2) clk_b = ~clk_b;

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
    #100;

    // Phase 2: Release reset, settle
    rst_n = 1;
    data_in = 1'b1;
    repeat (30) @(posedge clk_a);  // enough for both domains to settle

    // Verify clean
    has_x_before = (final_out === 1'bx);
    if (has_x_before) begin
      $display("FAIL: final_out has X before injection at t=%0t", $time);
      $finish;
    end
    $display("INFO: Clean at t=%0t, final_out=%b", $time, final_out);

    // Phase 3: Inject X at domain A stage 0
    @(posedge clk_a);
    force dut.ff_a0.Q = 1'bx;
    $display("INFO: Forced ff_a0.Q to X at t=%0t", $time);
    repeat(2) @(posedge clk_a);
    release dut.ff_a0.Q;
    $display("INFO: Released ff_a0.Q at t=%0t", $time);

    // Phase 4: Wait for propagation across CDC
    // 3 clk_a stages + 2 sync FFs + 2 clk_b stages = ~7 domain crossings
    repeat (20) @(posedge clk_b);

    // Phase 5: Self-check
    test_pass = (final_out === 1'bx);
    if (test_pass)
      $display("PASS: final_out has X at t=%0t, val=%b", $time, final_out);
    else
      $display("FAIL: no X in final_out at t=%0t, val=%b", $time, final_out);

    repeat (5) @(posedge clk_b);
    $finish;
  end

  initial #1000000 begin
    $display("TIMEOUT at t=%0t", $time);
    $finish;
  end

endmodule
