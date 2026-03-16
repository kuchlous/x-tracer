`timescale 1ns/1ps
module tb;
    reg        clk, rst_n;
    reg  [3:0] d;
    wire [3:0] q;

    reg4 dut (.q(q), .d(d), .clk(clk), .rst_n(rst_n));

    initial begin
        $dumpfile("sim.vcd");
        $dumpvars(0, tb);
    end

    // 10ns clock period
    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        rst_n = 0;
        d     = 4'b0000;
        // 8 cycles of reset
        repeat(8) @(posedge clk);
        rst_n = 1;
        // 8 settle cycles with d=0
        repeat(8) @(posedge clk);
        // Inject X on d[1] only; d[0,2,3] remain 0
        force tb.dut.d[1] = 1'bx;
        // One more posedge captures X into state[1]
        @(posedge clk); #1;
        $finish;
    end
endmodule
