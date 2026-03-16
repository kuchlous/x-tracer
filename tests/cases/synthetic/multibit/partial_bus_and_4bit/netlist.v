`timescale 1ns/1ps
module and4(output [3:0] y, input [3:0] a, b);
    and g0(y[0], a[0], b[0]);
    and g1(y[1], a[1], b[1]);
    and g2(y[2], a[2], b[2]);
    and g3(y[3], a[3], b[3]);
endmodule
