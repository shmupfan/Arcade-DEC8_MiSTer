// M4 board-level testbench top: d8_board + the SDRAM model on one DQ bus.
// Driven from sim/m4/tb_board.cpp.
module tb_board (
    input  logic        clk,
    input  logic        i_sdram_rst_n,
    input  logic        i_reset,
    input  logic        i_ioctl_download,
    input  logic        i_ioctl_wr,
    input  logic [26:0] i_ioctl_addr,
    input  logic [7:0]  i_ioctl_dout,
    input  logic [15:0] i_ioctl_index,
    output logic        o_ioctl_wait,
    input  logic [7:0]  i_in0,
    input  logic [7:0]  i_in1,
    input  logic [7:0]  i_in2,
    input  logic [7:0]  i_in3,
    input  logic [7:0]  i_coin,
    input  logic [3:0]  i_an0,
    input  logic [3:0]  i_an1,
    input  logic        i_pause,
    input  logic [1:0]  i_volume,
    output logic [7:0]  o_r,
    output logic [7:0]  o_g,
    output logic [7:0]  o_b,
    output logic        o_de,
    output logic        o_ce_pix,
    output logic [9:0]  o_pen,
    output logic        o_vbl,
    output logic        o_vs,
    output logic signed [15:0] o_audio,
    output logic [15:0] o_dbg_overruns,
    output logic [15:0] o_dbg_maxcyc,
    output logic [7:0]  o_dbg_verr,
    output logic [15:0] o_dbg_prom_late,
    output logic [15:0] o_dbg_unmapped,
    output logic [15:0] o_dbg_xacc,
    output logic [15:0] o_dbg_snd_unmapped,
    output logic [15:0] o_dbg_ref_forced,
    output logic [7:0]  o_dbg_cpu_maxlat,
    output logic [7:0]  o_dbg_sub_maxlat
);
  wire [12:0] A;
  wire [1:0]  BA;
  wire [15:0] DQ;
  wire        DQML, DQMH, nCS, nRAS, nCAS, nWE, CKE;
  logic hb, vb, hs;

  d8_board #(.SHORT_INIT(1'b1)) u_board (
    .clk(clk), .i_sdram_rst_n(i_sdram_rst_n), .i_reset(i_reset),
    .i_ioctl_download(i_ioctl_download), .i_ioctl_wr(i_ioctl_wr),
    .i_ioctl_addr(i_ioctl_addr), .i_ioctl_dout(i_ioctl_dout),
    .i_ioctl_index(i_ioctl_index), .o_ioctl_wait(o_ioctl_wait),
    .i_in0(i_in0), .i_in1(i_in1), .i_in2(i_in2), .i_in3(i_in3), .i_coin(i_coin),
    .i_an0(i_an0), .i_an1(i_an1), .i_pause(i_pause), .i_volume(i_volume),
    .o_machine(), .o_srdb(),
    .o_r(o_r), .o_g(o_g), .o_b(o_b), .o_hblank(hb), .o_vblank(vb),
    .o_hs(hs), .o_vs(o_vs), .o_de(o_de), .o_ce_pix(o_ce_pix),
    .o_audio(o_audio), .o_pen(o_pen), .o_vbl(o_vbl),
    .o_dbg_overruns(o_dbg_overruns), .o_dbg_maxcyc(o_dbg_maxcyc), .o_dbg_verr(o_dbg_verr),
    .o_dbg_prom_late(o_dbg_prom_late), .o_dbg_unmapped(o_dbg_unmapped), .o_dbg_xacc(o_dbg_xacc),
    .o_dbg_snd_unmapped(o_dbg_snd_unmapped),
    .o_dbg_ref_forced(o_dbg_ref_forced), .o_dbg_cpu_maxlat(o_dbg_cpu_maxlat),
    .o_dbg_sub_maxlat(o_dbg_sub_maxlat),
    .SDRAM_A(A), .SDRAM_BA(BA), .SDRAM_DQ(DQ), .SDRAM_DQML(DQML),
    .SDRAM_DQMH(DQMH), .SDRAM_nCS(nCS), .SDRAM_nRAS(nRAS), .SDRAM_nCAS(nCAS),
    .SDRAM_nWE(nWE), .SDRAM_CKE(CKE));

  sdram_model u_mem (
    .clk(clk), .A(A), .BA(BA), .DQ(DQ), .DQML(DQML), .DQMH(DQMH),
    .nCS(nCS), .nRAS(nRAS), .nCAS(nCAS), .nWE(nWE), .CKE(CKE));
endmodule
