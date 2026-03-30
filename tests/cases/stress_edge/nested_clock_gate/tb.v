// =============================================================================
// Stress Edge Test 5: Nested Clock Gating -- Testbench
//
// 3-level ICG hierarchy. X forced on innermost enable (en3).
// FF_A and FF_B on gclk_l3 should get corrupted clocks and produce X.
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter CLK_PERIOD    = 10;
  parameter SETTLE_CYCLES = 20;

  reg  clk    = 0;
  reg  rst_n  = 0;
  reg  en1    = 0;
  reg  en2    = 0;
  reg  en3    = 0;
  reg  data_a = 0;
  reg  data_b = 0;
  reg  data_c = 0;
  reg  data_d = 0;
  wire out_a, out_b, out_c, out_d;
  wire final_out;

  nested_clock_gate_net dut (
    .clk(clk), .rst_n(rst_n),
    .en1(en1), .en2(en2), .en3(en3),
    .data_a(data_a), .data_b(data_b),
    .data_c(data_c), .data_d(data_d),
    .out_a(out_a), .out_b(out_b),
    .out_c(out_c), .out_d(out_d),
    .final_out(final_out)
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
    en1 = 0; en2 = 0; en3 = 0;
    data_a = 0; data_b = 0; data_c = 0; data_d = 0;
    #80;

    // Phase 2: Release reset, enable all clock gates, settle
    rst_n = 1;
    en1 = 1; en2 = 1; en3 = 1;
    data_a = 1'b1; data_b = 1'b0; data_c = 1'b1; data_d = 1'b0;
    repeat (SETTLE_CYCLES) @(posedge clk);

    // Verify clean state
    has_x_before = (out_a === 1'bx) || (out_b === 1'bx);
    if (has_x_before) begin
      $display("FAIL: out_a/out_b has X before injection at t=%0t", $time);
      $finish;
    end
    $display("INFO: Clean at t=%0t, out_a=%b out_b=%b out_c=%b out_d=%b final_out=%b",
             $time, out_a, out_b, out_c, out_d, final_out);

    // Phase 3: Force innermost enable (en3) to X
    // This corrupts gclk_l3, which drives ff_a and ff_b
    @(posedge clk);
    force dut.icg_l3.en_lat = 1'bx;
    $display("INFO: Forced icg_l3.en_lat to X at t=%0t", $time);

    // Phase 4: Toggle data inputs to ensure FFs sample corrupted clock
    repeat (5) begin
      @(posedge clk);
      data_a = ~data_a;
      data_b = ~data_b;
    end

    repeat (5) @(posedge clk);
    release dut.icg_l3.en_lat;
    $display("INFO: Released icg_l3.en_lat at t=%0t", $time);

    // Phase 5: Wait a bit more
    repeat (10) @(posedge clk);

    // Phase 6: Self-check
    // out_a and out_b should have X (driven by corrupted gclk_l3)
    // out_c and out_d should be clean (on higher-level clocks)
    test_pass = (out_a === 1'bx) || (out_b === 1'bx) || (final_out === 1'bx);

    if (test_pass)
      $display("PASS: X propagated through clock gate. out_a=%b out_b=%b final_out=%b at t=%0t",
               out_a, out_b, final_out, $time);
    else
      $display("FAIL: no X in gclk_l3 leaf FFs at t=%0t, out_a=%b out_b=%b final_out=%b",
               $time, out_a, out_b, final_out);

    // Extra check: out_c and out_d should be clean
    if (out_c !== 1'bx && out_d !== 1'bx)
      $display("INFO: out_c and out_d are clean as expected (not on gclk_l3)");
    else
      $display("WARN: out_c=%b out_d=%b -- unexpected X on non-gclk_l3 FFs", out_c, out_d);

    repeat (5) @(posedge clk);
    $finish;
  end

  initial #500000 begin
    $display("TIMEOUT at t=%0t", $time);
    $finish;
  end

endmodule
