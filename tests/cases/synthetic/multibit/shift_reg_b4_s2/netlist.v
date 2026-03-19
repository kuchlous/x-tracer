`timescale 1ns/1ps
module shift_reg_dut (
    input  clk,
    input  rst_n,
    output [7:0] q
);
  reg [7:0] sr;
  initial sr = 8'b0;
  assign q = sr;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      sr <= 8'b0;
    else
      sr <= {sr[6:0], sr[7]};
  end
endmodule
