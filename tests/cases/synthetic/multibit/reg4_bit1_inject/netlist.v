`timescale 1ns/1ps
module reg4(output [3:0] q, input [3:0] d, input clk, rst_n);
    reg [3:0] state;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) state <= 4'b0000;
        else        state <= d;
    end
    assign q = state;
endmodule
