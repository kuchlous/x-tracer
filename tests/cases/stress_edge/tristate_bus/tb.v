// =============================================================================
// Stress Edge Test 4: Tri-State Bus -- Testbench
//
// 4 drivers on shared bus. Driver 2 is selected and its FF is forced to X.
// =============================================================================

`timescale 1ns/1ps

module tb;

  parameter CLK_PERIOD    = 10;
  parameter SETTLE_CYCLES = 20;

  reg        clk      = 0;
  reg        rst_n    = 0;
  reg  [3:0] drv_data = 4'b0000;
  reg  [3:0] drv_en   = 4'b0000;
  wire       final_out;

  tristate_bus_net dut (
    .clk(clk), .rst_n(rst_n),
    .drv_data(drv_data), .drv_en(drv_en),
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
    drv_data = 4'b1010;
    drv_en   = 4'b0000;  // all drivers off during reset
    #80;

    // Phase 2: Release reset, enable driver 0 only, settle
    rst_n = 1;
    drv_en = 4'b0001;    // only driver 0 active
    drv_data = 4'b1010;
    repeat (SETTLE_CYCLES) @(posedge clk);

    // Verify clean
    has_x_before = (final_out === 1'bx);
    if (has_x_before) begin
      $display("FAIL: final_out has X before injection at t=%0t", $time);
      $finish;
    end
    $display("INFO: Clean at t=%0t, final_out=%b", $time, final_out);

    // Phase 3: Switch to driver 2 and inject X on its source FF
    drv_en = 4'b0100;    // only driver 2 active
    drv_data[2] = 1'b1;
    @(posedge clk);
    @(posedge clk);

    // Now force driver 2's FF output to X
    force dut.ff_d2.Q = 1'bx;
    $display("INFO: Forced ff_d2.Q to X at t=%0t", $time);
    repeat(3) @(posedge clk);
    release dut.ff_d2.Q;
    $display("INFO: Released ff_d2.Q at t=%0t", $time);

    // Phase 4: Wait for propagation through bus -> recv FF -> out FF
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
