// =============================================================================
// X-Tracer Stress Test: Hierarchical LFSR Grid (Gate-Level)
//
// Architecture (6 levels of hierarchy):
//   stress_net
//   └── gen_block[R].gen_col[C]                  // grid of clusters
//       └── lfsr_cluster
//           └── gen_stage[S].gen_lane[L]          // pipeline of LFSR lanes
//               └── lfsr_core                     // N-bit LFSR
//                   ├── gen_chain[i]               // shift chain
//                   └── gen_ff[i] → dff_r          // DFF instances
//
// Default scale: 8×8 × 8×8 × 32 = 131,072 FFs, ~1M VCD signals
// =============================================================================

`timescale 1ns/1ps

// ---- Gate-level DFF with async active-low reset ----
module dff_r(input CLK, input D, input RST_N, output reg Q);
  initial Q = 1'b0;
  always @(posedge CLK or negedge RST_N)
    if (!RST_N) Q <= 1'b0;
    else Q <= D;
endmodule

// ---- Parameterized LFSR core, gate-level ----
// Feedback: XOR of the two highest bits (simple, works for any width ≥ 4)
module lfsr_core #(
  parameter WIDTH = 32
)(
  input              clk,
  input              rst_n,
  input  [WIDTH-1:0] seed_in,
  input              seed_valid,
  output [WIDTH-1:0] \lfsr.state ,
  output             \lfsr.fb
);

  // ---- Feedback: XOR of top 4 tap positions ----
  // Taps: WIDTH-1, WIDTH-3, WIDTH-4, WIDTH-6 (generic maximal-ish)
  wire \tap.xor_01 , \tap.xor_23 ;
  xor tap_x01 (\tap.xor_01 , \lfsr.state [WIDTH-1], \lfsr.state [WIDTH-3]);
  xor tap_x23 (\tap.xor_23 , \lfsr.state [WIDTH-4], \lfsr.state [WIDTH-6]);
  xor tap_xfb (\lfsr.fb , \tap.xor_01 , \tap.xor_23 );

  // ---- Bit 0: feedback XORed with gated seed ----
  wire \seed.masked_0 ;
  and seed_and0 (\seed.masked_0 , seed_in[0], seed_valid);
  wire \chain.d_0 ;
  xor chain_xor0 (\chain.d_0 , \lfsr.fb , \seed.masked_0 );

  // ---- Bits 1..WIDTH-1: shift + gated seed ----
  wire [WIDTH-1:1] \chain.d ;
  genvar i;
  generate
    for (i = 1; i < WIDTH; i = i + 1) begin: gen_chain
      wire \seed.masked ;
      and seed_and_i (\seed.masked , seed_in[i], seed_valid);
      xor chain_xor_i (\chain.d [i], \lfsr.state [i-1], \seed.masked );
    end
  endgenerate

  // ---- DFF instances ----
  dff_r ff0 (.CLK(clk), .D(\chain.d_0 ), .RST_N(rst_n), .Q(\lfsr.state [0]));
  generate
    for (i = 1; i < WIDTH; i = i + 1) begin: gen_ff
      dff_r ff_i (.CLK(clk), .D(\chain.d [i]), .RST_N(rst_n), .Q(\lfsr.state [i]));
    end
  endgenerate

endmodule

// ---- LFSR Cluster: pipeline of LFSR lanes ----
module lfsr_cluster #(
  parameter NUM_STAGES      = 8,
  parameter LANES_PER_STAGE = 8,
  parameter WIDTH           = 32
)(
  input              clk,
  input              rst_n,
  input  [WIDTH-1:0] \cluster.in ,
  input              \cluster.in_valid ,
  output [WIDTH-1:0] \cluster.out
);

  wire [WIDTH-1:0] stage_out [0:NUM_STAGES-1][0:LANES_PER_STAGE-1];

  genvar s, l;
  generate
    for (s = 0; s < NUM_STAGES; s = s + 1) begin: gen_stage
      for (l = 0; l < LANES_PER_STAGE; l = l + 1) begin: gen_lane

        wire [WIDTH-1:0] \lane.seed ;
        wire             \lane.seed_valid ;

        if (s == 0 && l == 0) begin: gen_first
          assign \lane.seed       = \cluster.in ;
          assign \lane.seed_valid = \cluster.in_valid ;
        end else if (l == 0) begin: gen_stage_link
          assign \lane.seed       = stage_out[s-1][LANES_PER_STAGE-1];
          assign \lane.seed_valid = 1'b1;
        end else begin: gen_lane_link
          assign \lane.seed       = stage_out[s][l-1];
          assign \lane.seed_valid = 1'b1;
        end

        lfsr_core #(.WIDTH(WIDTH)) core (
          .clk        (clk),
          .rst_n      (rst_n),
          .seed_in    (\lane.seed ),
          .seed_valid (\lane.seed_valid ),
          .\lfsr.state (stage_out[s][l]),
          .\lfsr.fb   ()
        );

      end
    end
  endgenerate

  assign \cluster.out = stage_out[NUM_STAGES-1][LANES_PER_STAGE-1];

endmodule

// ---- Top-level: grid of clusters ----
module stress_net #(
  parameter BLOCK_ROWS         = 8,
  parameter BLOCK_COLS         = 8,
  parameter STAGES_PER_CLUSTER = 8,
  parameter LANES_PER_STAGE    = 8,
  parameter LFSR_WIDTH         = 32
)(
  input                    clk,
  input                    rst_n,
  input  [LFSR_WIDTH-1:0]  inject_data,
  input                    inject_valid,
  output [LFSR_WIDTH-1:0]  final_out
);

  wire [LFSR_WIDTH-1:0] block_out [0:BLOCK_ROWS-1][0:BLOCK_COLS-1];

  genvar r, c;
  generate
    for (r = 0; r < BLOCK_ROWS; r = r + 1) begin: gen_block
      for (c = 0; c < BLOCK_COLS; c = c + 1) begin: gen_col

        wire [LFSR_WIDTH-1:0] \cluster.seed ;
        wire                  \cluster.seed_valid ;

        if (r == 0 && c == 0) begin: gen_inject
          assign \cluster.seed       = inject_data;
          assign \cluster.seed_valid = inject_valid;
        end else if (c == 0) begin: gen_row_link
          assign \cluster.seed       = block_out[r-1][BLOCK_COLS-1];
          assign \cluster.seed_valid = 1'b1;
        end else begin: gen_col_link
          assign \cluster.seed       = block_out[r][c-1];
          assign \cluster.seed_valid = 1'b1;
        end

        lfsr_cluster #(
          .NUM_STAGES     (STAGES_PER_CLUSTER),
          .LANES_PER_STAGE(LANES_PER_STAGE),
          .WIDTH          (LFSR_WIDTH)
        ) cluster_inst (
          .clk              (clk),
          .rst_n            (rst_n),
          .\cluster.in      (\cluster.seed ),
          .\cluster.in_valid (\cluster.seed_valid ),
          .\cluster.out     (block_out[r][c])
        );

      end
    end
  endgenerate

  assign final_out = block_out[BLOCK_ROWS-1][BLOCK_COLS-1];

endmodule
