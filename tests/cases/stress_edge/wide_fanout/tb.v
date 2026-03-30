// =============================================================================
// Stress Edge Test 2: Wide Fanout Reconvergence -- Testbench
//
// Single source fans out to 32 paths through different gate types,
// reconverges via XOR tree. X injected at source FF, queried at output.
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter CLK_PERIOD    = 10;
  parameter SETTLE_CYCLES = 20;

  reg         clk     = 0;
  reg         rst_n   = 0;
  reg         src_in  = 0;
  reg  [31:0] side_in = 32'h0;
  wire        final_out;

  wide_fanout_net dut (
    .clk(clk), .rst_n(rst_n),
    .src_in(src_in), .side_in(side_in),
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
    src_in = 0;
    // AND paths need side_in=1 to propagate X; OR paths need side_in=0
    // XOR paths propagate X regardless; BUF paths ignore side_in
    // Set AND side_in bits [7:0] = 1, OR bits [15:8] = 0, rest don't matter
    side_in = 32'h000000FF;
    #80;

    // Phase 2: Release reset, settle
    rst_n = 1;
    src_in = 1'b1;
    repeat (SETTLE_CYCLES) @(posedge clk);

    // Verify clean
    has_x_before = (final_out === 1'bx);
    if (has_x_before) begin
      $display("FAIL: final_out has X before injection at t=%0t", $time);
      $finish;
    end
    $display("INFO: Clean at t=%0t, final_out=%b", $time, final_out);

    // Phase 3: Inject X at the source FF
    @(posedge clk);
    force dut.ff_src.Q = 1'bx;
    $display("INFO: Forced ff_src.Q to X at t=%0t", $time);
    repeat(2) @(posedge clk);
    release dut.ff_src.Q;
    $display("INFO: Released ff_src.Q at t=%0t", $time);

    // Phase 4: Wait for propagation (2 FF stages: src -> path FFs -> out FF)
    repeat (10) @(posedge clk);

    // Phase 5: Self-check
    test_pass = (final_out === 1'bx);
    if (test_pass)
      $display("PASS: final_out has X at t=%0t, val=%b", $time, final_out);
    else
      $display("FAIL: no X in final_out at t=%0t, val=%b", $time, final_out);

    repeat (5) @(posedge clk);
    $finish;
  end

  initial #500000 begin
    $display("TIMEOUT at t=%0t", $time);
    $finish;
  end

endmodule
