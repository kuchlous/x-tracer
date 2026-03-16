`timescale 1ns/1ps
module tb;
    reg  [3:0] a, b;
    wire [3:0] y;

    and4 dut (.y(y), .a(a), .b(b));

    initial begin
        $dumpfile("sim.vcd");
        $dumpvars(0, tb);
    end

    initial begin
        // All inputs known at t=0: a=0, b=1111
        a = 4'b0000;
        b = 4'b1111;
        // Settle: combinational, wait 10ns
        #10;
        // Inject X on bit 0 only — Layer 2 clean before this point
        force tb.dut.a[0] = 1'bx;
        // Wait 10ns for combinational propagation
        #10;
        $finish;
    end
endmodule
