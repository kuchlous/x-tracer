`timescale 1ns/1ps
module tb;
    reg  [3:0] a, b;
    wire [3:0] y;

    and4 dut (.y(y), .a(a), .b(b));

    initial begin
        $dumpfile("sim_no_inject.vcd");
        $dumpvars(0, tb);
    end

    initial begin
        a = 4'b0000;
        b = 4'b1111;
        #10;
        // No injection
        #10;
        $finish;
    end
endmodule
