`timescale 1ns/1ps
module ff_chain(output q1, input d, clk, rst_n);
  reg ff0, ff1;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin ff0<=0; ff1<=0; end
    else begin ff0<=d; ff1<=ff0; end
  end
  assign q1 = ff1;
endmodule
