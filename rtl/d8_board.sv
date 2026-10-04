// DEC8 board (PLAN M4): everything below the MiSTer framework.
// d8_sys (CPUs, MCU, video, sound board) + d8_sdram, plus the ioctl download
// handling, so the board simulation runs exactly what the RBF contains.
//
// ioctl indices (MRA, tools/make_mra.py):
//   0    ROM stream (docs/m4_findings.md 2):
//          0x000000-0x087FFF  sdram.bin bytes 0-0x87FFF (tools/build_regions.py
//                             SDRAM_SLOTS: main program and banks, sub CPU,
//                             audio CPU, MCU, PROMs)
//          0x088000-0x0FFFFF  zero fill
//          0x100000-0x207FFF  the graphics port image (tools/gfx_layout.py)
//        Everything goes to the SDRAM; on the way past, the MCU program
//        (0x080000-0x080FFF) is copied into d8_sys's MCU ROM and the sound
//        program (0x068000-0x06FFFF, the 6502's 8000-FFFF) into the sound
//        board's ROM, as the M2/M3 harness loads them.
//   1    machine byte: bits 1:0 = machine (0 Last Mission, 1 Gondomania,
//        2 SRD), bit 2 = srdarwinb (no MCU). Sampled while the core is held
//        in reset.
//   254  DIP switches: byte 0 = DSW0 (SW1), byte 1 = DSW1 (SW2), MAME's
//        port layout.
// The core is held in reset during any download and until the SDRAM is
// initialised.
//
// srdarwinb's sprite ROMs hold bytes 1 and 2 of every 4-byte group swapped
// (MAME init_srdarwinb, dec8.cpp L4097-4110, swaps them back after loading).
// The MRA streams the ROMs as dumped and the board swaps the sprite word
// address bits 0 and 1 instead (every lane of a sprite word comes from the
// same region offset, tools/gfx_layout.py), which reads the same data as
// MAME's fixed-up region.

module d8_board #(
    parameter bit  SHORT_INIT = 1'b0
) (
    input  logic        clk,            // 96 MHz
    input  logic        i_sdram_rst_n,  // PLL locked
    input  logic        i_reset,

    input  logic        i_ioctl_download,
    input  logic        i_ioctl_wr,
    input  logic [26:0] i_ioctl_addr,
    input  logic [7:0]  i_ioctl_dout,
    input  logic [15:0] i_ioctl_index,
    output logic        o_ioctl_wait,

    // inputs as MAME's ports (active low, vblank bits merged in d8_sys)
    input  logic [7:0]  i_in0,
    input  logic [7:0]  i_in1,
    input  logic [7:0]  i_in2,
    input  logic [7:0]  i_in3,
    input  logic [7:0]  i_coin,
    input  logic [3:0]  i_an0,          // Gondomania rotary positions 0-11
    input  logic [3:0]  i_an1,
    input  logic        i_pause,
    input  logic [1:0]  i_volume,       // OSD volume: 0 normal, 1 +6 dB, 2 -6 dB, 3 -12 dB

    output logic [1:0]  o_machine,
    output logic        o_srdb,

    output logic [7:0]  o_r,
    output logic [7:0]  o_g,
    output logic [7:0]  o_b,
    output logic        o_hblank,
    output logic        o_vblank,
    output logic        o_hs,
    output logic        o_vs,
    output logic        o_de,
    output logic        o_ce_pix,
    output logic signed [15:0] o_audio,
    output logic [9:0]  o_pen,          // sim/debug: palette index of the pixel
    output logic        o_vbl,          // sim/debug: start of line 248

    // gate counters
    output logic [15:0] o_dbg_overruns,
    output logic [15:0] o_dbg_maxcyc,
    output logic [7:0]  o_dbg_verr,
    output logic [15:0] o_dbg_prom_late,
    output logic [15:0] o_dbg_unmapped,
    output logic [15:0] o_dbg_xacc,
    output logic [15:0] o_dbg_snd_unmapped,
    output logic [15:0] o_dbg_ref_forced,
    output logic [7:0]  o_dbg_cpu_maxlat,
    output logic [7:0]  o_dbg_sub_maxlat,

    output logic [12:0] SDRAM_A,
    output logic [1:0]  SDRAM_BA,
    inout  wire  [15:0] SDRAM_DQ,
    output logic        SDRAM_DQML,
    output logic        SDRAM_DQMH,
    output logic        SDRAM_nCS,
    output logic        SDRAM_nRAS,
    output logic        SDRAM_nCAS,
    output logic        SDRAM_nWE,
    output logic        SDRAM_CKE
);

  // ------------------------------------------------------------------ ioctl
  wire rom_wr = i_ioctl_download && i_ioctl_wr && i_ioctl_index[7:0] == 8'd0;

  /* verilator lint_off PROCASSINIT */
  logic [2:0] mbyte = 3'd0;             // power-on values, as Dooyong
  logic [7:0] dsw0 = 8'hFF, dsw1 = 8'hFF;
  /* verilator lint_on PROCASSINIT */
  always_ff @(posedge clk) begin
    if (i_ioctl_wr && i_ioctl_index[7:0] == 8'd1 && i_ioctl_addr == 27'd0)
      mbyte <= i_ioctl_dout[2:0];
    if (i_ioctl_wr && i_ioctl_index[7:0] == 8'd254) begin
      if (i_ioctl_addr == 27'd0) dsw0 <= i_ioctl_dout;
      if (i_ioctl_addr == 27'd1) dsw1 <= i_ioctl_dout;
    end
  end
  wire [1:0] machine = (mbyte[1:0] == 2'd3) ? 2'd0 : mbyte[1:0];
  wire       srdb    = mbyte[2];
  assign o_machine = machine;
  assign o_srdb    = srdb;

  // block RAM copies of the MCU and sound programs (registered, one write
  // per ioctl byte; the core is in reset during the download)
  logic        mcu_we, snd_we;
  logic [11:0] mcu_a;
  logic [14:0] snd_a;
  logic [7:0]  ld_d;
  always_ff @(posedge clk) begin
    mcu_we <= rom_wr && i_ioctl_addr[26:12] == 15'h0080;           // 0x080000-0x080FFF
    snd_we <= rom_wr && i_ioctl_addr[26:15] == 12'h00D;            // 0x068000-0x06FFFF
    mcu_a  <= i_ioctl_addr[11:0];
    snd_a  <= i_ioctl_addr[14:0];
    ld_d   <= i_ioctl_dout;
  end

  // ------------------------------------------------------------------ SDRAM
  logic        core_rst_n;
  logic        core_run /* verilator public_flat_rd */;
  logic        sd_ready;
  logic        prom_req, prom_ok, srom_req, srom_ok;
  logic [20:0] prom_addr, srom_addr;
  logic [7:0]  prom_data, srom_data;
  logic        rom_req /* verilator public_flat_rd */, rom_gnt /* verilator public_flat_rd */, rom_rv /* verilator public_flat_rd */;
  logic [21:0] rom_addr /* verilator public_flat_rd */, gfx_addr;
  logic [31:0] rom_data /* verilator public_flat_rd */;

  // srdarwinb: sprite word address bits 0 and 1 swapped (byte address bits
  // 2 and 3) in the sprite block 0x080000-0x0FFFFF
  wire spr_blk = rom_addr[21:19] == 3'b001;
  assign gfx_addr = (srdb && spr_blk) ? {rom_addr[21:4], rom_addr[2], rom_addr[3], rom_addr[1:0]}
                                      : rom_addr;

  d8_sdram #(.P_SHORT_INIT(SHORT_INIT)) u_sdram (
    .clk(clk), .rst_n(i_sdram_rst_n), .o_ready(sd_ready),
    .i_dl_wr(rom_wr), .i_dl_addr(i_ioctl_addr[23:0]), .i_dl_data(i_ioctl_dout),
    .o_dl_busy(o_ioctl_wait),
    .i_cpu_run(core_run), .i_cpu_req(prom_req), .i_cpu_addr(prom_addr[19:0]),
    .o_cpu_data(prom_data), .o_cpu_ok(prom_ok),
    .i_sub_req(srom_req), .i_sub_addr(srom_addr[19:0]), .o_sub_data(srom_data), .o_sub_ok(srom_ok),
    .i_gfx_req(rom_req), .i_gfx_addr(gfx_addr), .o_gfx_gnt(rom_gnt),
    .o_gfx_rv(rom_rv), .o_gfx_data(rom_data),
    .o_dbg_refreshes(), .o_dbg_ref_forced(o_dbg_ref_forced),
    .o_dbg_cpu_maxlat(o_dbg_cpu_maxlat), .o_dbg_sub_maxlat(o_dbg_sub_maxlat), .o_dbg_dl_words(),
    .SDRAM_A(SDRAM_A), .SDRAM_BA(SDRAM_BA), .SDRAM_DQ(SDRAM_DQ),
    .SDRAM_DQML(SDRAM_DQML), .SDRAM_DQMH(SDRAM_DQMH),
    .SDRAM_nCS(SDRAM_nCS), .SDRAM_nRAS(SDRAM_nRAS), .SDRAM_nCAS(SDRAM_nCAS),
    .SDRAM_nWE(SDRAM_nWE), .SDRAM_CKE(SDRAM_CKE));

  // ------------------------------------------------------------------ core
  always_ff @(posedge clk) core_rst_n <= !i_reset && !i_ioctl_download && sd_ready;

  logic signed [15:0] mix /* verilator public_flat_rd */;

  // FREE_TIMING: sync keeps running (black picture) during the ROM download
  // and SDRAM init; d8_sys releases the core on the raster's power-on phase
  // (core_run), as the 1945k III and Tecmo 16 cores.
  d8_sys #(.FREE_TIMING(1'b1)) u_sys (
    .clk(clk), .rst_n(core_rst_n), .i_pwr_rst_n(i_sdram_rst_n), .o_run(core_run),
    .i_machine(machine), .i_srdb(srdb), .i_pause(i_pause),
    .i_in0(i_in0), .i_in1(i_in1), .i_in2(i_in2), .i_in3(i_in3), .i_coin(i_coin),
    .i_dsw0(dsw0), .i_dsw1(dsw1), .i_an0(i_an0), .i_an1(i_an1),
    .o_prom_req(prom_req), .o_prom_addr(prom_addr), .i_prom_data(prom_data), .i_prom_ok(prom_ok),
    .o_srom_req(srom_req), .o_srom_addr(srom_addr), .i_srom_data(srom_data), .i_srom_ok(srom_ok),
    .i_mcu_we(mcu_we), .i_mcu_addr(mcu_a), .i_mcu_din(ld_d),
    .o_rom_req(rom_req), .o_rom_addr(rom_addr),
    .i_rom_gnt(rom_gnt), .i_rom_rv(rom_rv), .i_rom_data(rom_data),
    .o_snd_wr(), .o_snd_data(),
    .i_snd_we(snd_we), .i_snd_addr(snd_a), .i_snd_din(ld_d),
    .o_fm(), .o_ssg(), .o_opl(), .o_audio(mix), .o_dbg_snd_unmapped(o_dbg_snd_unmapped),
    .o_r(o_r), .o_g(o_g), .o_b(o_b), .o_de(o_de),
    .o_hblank(o_hblank), .o_vblank(o_vblank), .o_hs(o_hs), .o_vs(o_vs),
    .o_vbl(o_vbl), .o_ce_pix(o_ce_pix), .o_pen(o_pen),
    .o_dbg_overruns(o_dbg_overruns), .o_dbg_maxcyc(o_dbg_maxcyc), .o_dbg_verr(o_dbg_verr),
    .o_dbg_prom_late(o_dbg_prom_late), .o_dbg_unmapped(o_dbg_unmapped), .o_dbg_xacc(o_dbg_xacc));

  // ------------------------------------------------------------------ audio
  // d8_snd's mix (YM2203 FM + SSG + OPL, m3_findings) times a per-machine
  // gain in 1/16 steps, then the OSD volume, saturated. The boards set the
  // level with a volume pot after the amplifier, so absolute level is ours
  // to choose. Reference: Final Star Force on the Tecmo 16 core, gameplay
  // 1 s RMS median -16.4 dBFS. Measured on the M3 runs (mix channel, 1 s
  // RMS median / peak sample): Last Mission attract -30.8 dBFS, play -28.2,
  // peak 13,462; Gondomania attract -26.5, play -27.2, peak 12,176; SRD
  // attract -21.1, play -23.3, peak 18,934. The gains bring each game's
  // loudest measured sample to -0.6 to -0.2 dBFS, no clipping on any run:
  //   Last Mission x2.375 (38/16): play median -20.7 dBFS, peak 31,972
  //   Gondomania   x2.5   (40/16): play median -19.2 dBFS, peak 30,440
  //   SRD          x1.6875 (27/16): play median -18.8 dBFS, peak 31,951
  // Both multiplier operands signed (Dooyong landmine: one unsigned operand
  // makes the product unsigned).
  logic signed [6:0]  gain;
  logic signed [23:0] prod, amp;
  always_comb begin
    case (machine)
      2'd1:    gain = 7'sd40;
      2'd2:    gain = 7'sd27;
      default: gain = 7'sd38;
    endcase
  end
  logic signed [15:0] mix_q;
  always_ff @(posedge clk) begin                 // registered twice (timing)
    mix_q <= mix;
    prod  <= mix_q * gain;
  end
  always_comb begin
    case (i_volume)
      2'd1:    amp = prod >>> 3;
      2'd2:    amp = prod >>> 5;
      2'd3:    amp = prod >>> 6;
      default: amp = prod >>> 4;
    endcase
  end
  always_ff @(posedge clk)
    o_audio <= (amp > 24'sd32767)  ? 16'sh7FFF :
               (amp < -24'sd32768) ? 16'sh8000 : amp[15:0];

endmodule
