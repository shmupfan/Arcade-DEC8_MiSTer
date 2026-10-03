// DEC8 video for Last Mission, Gondomania and SRD: Super Real Darwin (PLAN M1).
//
// Reference model: sim/oracle/d8_render.py, pixel-exact against MAME 0.288
// on every M0 capture. "spec N" = docs/dec8_system_spec.md; dec8/v/krn line
// numbers = reference/mame/v0288/dec8.cpp, dec8_v.cpp, deckarn.cpp.
//
// Contents:
//   - raster: 384 pixels per line at a 6 MHz pixel enable (96 MHz / 16),
//     272 lines, visible 256 x 240 at lines 8-247, vblank from line 248
//     (dec8:1977-1981, "DECO video CRTC, matches PCB measurements")
//   - CPU-side RAMs, byte wide on the CPU side (the 6809/6309 is 8-bit),
//     16-bit words on the renderer side: palette {ext, RAM} 1,024 entries,
//     fix RAM and bg RAM 2 KB each (word i = bytes 2i, 2i+1, high byte
//     first, as every tile_info in dec8_v.cpp reads them), sprite RAM 2 KB
//     with its buffer (snapram MODE 1: on `i_spr_copy` the buffer becomes
//     the RAM as it stood at that clock, copy-before-write; MAME copies
//     instantly, spec 9, research item R3)
//   - LATCH = 0 (default, Lee 2026-10-02, PLAN 5.2): the renderer reads tile
//     RAM, palette, scroll and flip live while the frame is drawn (most
//     plausible PCB behaviour, unconfirmed, R5). LATCH = 1: those are
//     snapshotted at the start of line LATCH_LINE. MAME draws each frame
//     once at vblank; m1_findings lists every frame where that differs.
//   - KRN_FLIP = 0 (default, MAME, PLAN 5.4): the Karnov sprites of
//     lastmisn/gondo are not flipped with the screen (dec8.cpp never sets
//     the sprite chip's flip flag, R7); 1 applies the chip's flip path
//     (krn:79-86) whenever the screen is flipped
//   - line renderer: during line L-1 the tile passes and the sprite pass
//     build line L into three double line buffers (bg, fix, sprites);
//     scan-out mixes them by the machine's priority rule and looks the
//     colour up in the palette (DECO RM-C3 resistor weights, decrmc3)
//
// Graphics ROM port: one port, pipelined, in-order returns; 32-bit words of
// 8 pixels in the plane-byte layout of tools/gfx_layout.py (bg tiles at
// 0x000000, sprites 0x080000, fix chars 0x100000).
// ROM traffic per line: bg 17 tiles x 2 words, fix 32 tiles x 1 word,
// sprites 2 words per sprite crossing the line. One writer drains the
// returned words at one pixel per clock.

module d8_video #(
    parameter bit LATCH      = 1'b0,
    parameter int LATCH_LINE = 6,
    parameter bit KRN_FLIP   = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        ce_pix,          // 6 MHz: exactly one clock in 16
    input  logic [1:0]  i_machine,       // 0 lastmisn, 1 gondo, 2 srdarwin

    // CPU side (decoded by the system, M2): byte address within each RAM
    input  logic [10:0] i_cpu_addr,
    input  logic [7:0]  i_cpu_din,
    input  logic        i_pal_we,        // palette RAM byte (entry = addr[9:0])
    input  logic        i_palx_we,       // palette ext byte (entry = addr[9:0])
    input  logic        i_fix_we,        // fix RAM, 2 KB
    input  logic        i_bg_we,         // bg RAM, 2 KB
    input  logic        i_spr_we,        // sprite RAM, 2 KB (srdarwin uses 512 bytes)
    input  logic        i_spr_copy,      // sprite buffer copy (spec 9)
    input  logic        i_scr_we,        // m_scroll[i_scr_sel] = din (MAME's 4 scroll bytes)
    input  logic [1:0]  i_scr_sel,
    input  logic        i_flip_we,       // flip = din[0]
    output logic [7:0]  o_pal_dout,
    output logic [7:0]  o_palx_dout,
    output logic [7:0]  o_fix_dout,
    output logic [7:0]  o_bg_dout,
    output logic [7:0]  o_spr_dout,

    // graphics ROM port (byte address, tools/gfx_layout.py)
    output logic        o_rom_req,
    output logic [21:0] o_rom_addr,
    input  logic        i_rom_gnt,
    input  logic        i_rom_rv,
    input  logic [31:0] i_rom_data,

    // video
    output logic [7:0]  o_r,
    output logic [7:0]  o_g,
    output logic [7:0]  o_b,
    output logic        o_de,
    output logic        o_hblank,
    output logic        o_vblank,
    output logic        o_hs,
    output logic        o_vs,
    output logic        o_vbl,           // one clk at the start of line 248 (NMI, MCU INT0)
    output logic        o_busy,          // a snapshot engine is running
    output logic        o_hold,          // a CPU write is held by a snapshot engine

    // gate counters / debug
    output logic [15:0] o_dbg_overruns,
    output logic [15:0] o_dbg_maxcyc,
    output logic [7:0]  o_dbg_err,
    output logic [9:0]  o_dbg_pen        // palette index of the output pixel
);

  localparam logic [21:0] BG_BASE  = 22'h000000;
  localparam logic [21:0] SPR_BASE = 22'h080000;
  localparam logic [21:0] FIX_BASE = 22'h100000;
  localparam int H_ACT = 256, H_TOTAL = 384, V_TOTAL = 272;
  localparam int V_VIS0 = 8, V_VIS1 = 247, V_VBL = 248;
  // sync positions are not in the driver; placed inside the blanking
  localparam int HS_START = 304, HS_END = 336;
  localparam int VS_START = 256;

  wire lm = i_machine == 2'd0;
  wire go_m = i_machine == 2'd1;
  wire sr = i_machine == 2'd2;

  // ================================================================ timing
  logic [8:0] hcnt /* verilator public_flat_rd */;
  logic [8:0] vcnt /* verilator public_flat_rd */;
  // power-on phase as MAME: the screen starts at the first vblank line
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      hcnt <= '0;
      vcnt <= 9'(V_VBL);
    end else if (ce_pix) begin
      if (hcnt == 9'(H_TOTAL - 1)) begin
        hcnt <= '0;
        vcnt <= (vcnt == 9'(V_TOTAL - 1)) ? 9'd0 : vcnt + 9'd1;
      end else hcnt <= hcnt + 9'd1;
    end
  end
  wire last_px    = ce_pix && hcnt == 9'(H_TOTAL - 1);
  wire vbl_start  = last_px && vcnt == 9'(V_VBL - 1);
  wire latch_now  = last_px && vcnt == 9'(LATCH_LINE - 1);
  wire line_start = ce_pix && hcnt == 9'd0;
  always_ff @(posedge clk) o_vbl <= rst_n && vbl_start;

  // ================================================================ registers
  logic [7:0] sc [0:3];          // MAME m_scroll[0..3]: x MSB, x LSB, y MSB, y LSB
  logic       flip_r;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      for (int i = 0; i < 4; i++) sc[i] <= '0;
      flip_r <= 1'b0;
    end else begin
      if (i_scr_we) sc[i_scr_sel] <= i_cpu_din;
      if (i_flip_we) flip_r <= i_cpu_din[0];
    end
  end
  // scroll = (m_scroll[0] << 8) + m_scroll[1] (v:336-337, 435, 512-513); the
  // tilemaps are 512 wide (and 512 or 256 high), so only 9 bits matter
  wire [8:0] sx_live = {sc[0][0], 8'd0} + {1'b0, sc[1]};
  wire [8:0] sy_live = {sc[2][0], 8'd0} + {1'b0, sc[3]};

  logic [8:0] v_sx, v_sy;
  logic       v_flip;
  generate
    if (LATCH) begin : g_latch_regs
      always_ff @(posedge clk) if (latch_now) begin
        v_sx <= sx_live; v_sy <= sy_live; v_flip <= flip_r;
      end
    end else begin : g_live_regs
      always_comb begin
        v_sx = sx_live; v_sy = sy_live; v_flip = flip_r;
      end
    end
  endgenerate

  // ================================================================ RAMs
  // CPU byte to 16-bit word: even byte = high lane (tile_info reads
  // ram[2i] << 8 | ram[2i+1]); palette word = {ext, RAM}
  localparam int TMODE = LATCH ? 1 : 0;
  wire [1:0]  be_tile = i_cpu_addr[0] ? 2'b01 : 2'b10;
  wire [15:0] din16   = {i_cpu_din, i_cpu_din};
  logic [9:0] pal_va, fix_va, bg_va, spr_va;
  logic [15:0] pal_q, fix_q, bg_q, spr_q;
  logic [15:0] pal_cq, fix_cq, bg_cq, spr_cq;
  logic [3:0] busy_v, hold_v;
  logic [7:0] err_v [0:3];

  d8_snapram #(.AW(10), .MODE(TMODE)) u_pal (
      .clk, .rst_n, .i_cpu_addr(i_cpu_addr[9:0]), .i_cpu_din(din16),
      .i_cpu_be(i_palx_we ? 2'b10 : 2'b01), .i_cpu_we(i_pal_we || i_palx_we),
      .o_cpu_dout(pal_cq), .i_snap(latch_now), .o_busy(busy_v[0]), .o_hold(hold_v[0]), .o_err(err_v[0]),
      .i_vid_addr(pal_va), .o_vid_q(pal_q));
  d8_snapram #(.AW(10), .MODE(TMODE)) u_fix (
      .clk, .rst_n, .i_cpu_addr(i_cpu_addr[10:1]), .i_cpu_din(din16), .i_cpu_be(be_tile), .i_cpu_we(i_fix_we),
      .o_cpu_dout(fix_cq), .i_snap(latch_now), .o_busy(busy_v[1]), .o_hold(hold_v[1]), .o_err(err_v[1]),
      .i_vid_addr(fix_va), .o_vid_q(fix_q));
  d8_snapram #(.AW(10), .MODE(TMODE)) u_bg (
      .clk, .rst_n, .i_cpu_addr(i_cpu_addr[10:1]), .i_cpu_din(din16), .i_cpu_be(be_tile), .i_cpu_we(i_bg_we),
      .o_cpu_dout(bg_cq), .i_snap(latch_now), .o_busy(busy_v[2]), .o_hold(hold_v[2]), .o_err(err_v[2]),
      .i_vid_addr(bg_va), .o_vid_q(bg_q));
  d8_snapram #(.AW(10), .MODE(1)) u_spr (
      .clk, .rst_n, .i_cpu_addr(i_cpu_addr[10:1]), .i_cpu_din(din16), .i_cpu_be(be_tile), .i_cpu_we(i_spr_we),
      .o_cpu_dout(spr_cq), .i_snap(i_spr_copy), .o_busy(busy_v[3]), .o_hold(hold_v[3]), .o_err(err_v[3]),
      .i_vid_addr(spr_va), .o_vid_q(spr_q));
  assign o_busy = |busy_v;
  assign o_hold = |hold_v;
  always_comb begin
    o_dbg_err = '0;
    for (int i = 0; i < 4; i++) o_dbg_err = o_dbg_err | err_v[i];
  end
  // CPU reads: the lane of the address presented one clock earlier
  logic lane_r;
  always_ff @(posedge clk) lane_r <= i_cpu_addr[0];
  assign o_pal_dout  = pal_cq[7:0];
  assign o_palx_dout = pal_cq[15:8];
  assign o_fix_dout  = lane_r ? fix_cq[7:0] : fix_cq[15:8];
  assign o_bg_dout   = lane_r ? bg_cq[7:0] : bg_cq[15:8];
  assign o_spr_dout  = lane_r ? spr_cq[7:0] : spr_cq[15:8];

  // ================================================================ renderer
  wire [8:0] next_line = (vcnt == 9'(V_TOTAL - 1)) ? 9'd0 : vcnt + 9'd1;
  wire       want_line = line_start && next_line >= 9'(V_VIS0) && next_line <= 9'(V_VIS1);

  logic        busy, pend;
  logic [8:0]  pend_line;
  logic [7:0]  r_line;          // display line of the pass (8-247)
  logic        r_flip;
  logic [8:0]  r_sx, r_sy;
  logic [15:0] cyc, maxcyc, overruns;
  wire         go = !busy && (want_line || pend);
  wire [8:0]   go_line = want_line ? next_line : pend_line;

  // ---- tile issuer: layer 0 bg (17 tiles x 2 words), layer 1 fix (32 x 1)
  localparam logic [1:0] T_IDLE = 2'd0, T_ADDR = 2'd1, T_WAIT = 2'd2, T_ISS = 2'd3;
  logic [1:0]  t_st;
  logic        t_layer;
  logic [5:0]  t_k;
  logic        t_j;
  logic        t_done;
  logic [15:0] t_w;              // tile RAM word
  logic        t_lane;           // srdarwin fix: byte lane of the tile

  // bg logical line: (line + sy) unflipped, (sy + 255 - line) flipped (tilemap.cpp,
  // spec 3); srdarwin has no y scroll and is 256 high
  wire [8:0]   r_syb   = sr ? 9'd0 : r_sy;
  wire [8:0]   bg_ly0  = r_flip ? (r_syb + 9'd255 - {1'b0, r_line}) : ({1'b0, r_line} + r_syb);
  wire [8:0]   bg_ly   = sr ? {1'b0, bg_ly0[7:0]} : bg_ly0;
  wire [7:0]   fx_ly   = r_flip ? 8'd255 - r_line : r_line;
  wire [4:0]   bg_row  = sr ? {1'b0, bg_ly[7:4]} : bg_ly[8:4];
  wire [4:0]   bg_col  = r_sx[8:4] + t_k[4:0];
  wire [4:0]   fx_row  = fx_ly[7:3];
  wire [4:0]   fx_col  = t_k[4:0];
  // bg tile RAM word: lastmisn_scan_rows (v:359-363), gondo/srdarwin row-major
  wire [9:0]   bg_idx  = lm ? {bg_row[4], bg_col[4], bg_row[3:0], bg_col[3:0]}
                      : sr ? {1'b0, bg_row[3:0], bg_col} : {bg_row, bg_col};
  wire [9:0]   fx_tile = {fx_row, fx_col};
  assign bg_va  = bg_idx;
  assign fix_va = sr ? {1'b0, fx_tile[9:1]} : fx_tile;

  // tile word decode
  wire [11:0]  bg_code = sr ? {2'd0, t_w[9:0]} : t_w[11:0];
  wire [3:0]   bg_attr = sr ? {2'd0, t_w[13:12]} : t_w[15:12];
  wire [7:0]   sr_ch   = t_lane ? t_w[7:0] : t_w[15:8];
  wire [9:0]   fx_code = sr ? {2'd0, sr_ch} : t_w[9:0];             // chars wrap at 1,024
  wire [3:0]   fx_attr = sr ? 4'd0 : lm ? {2'd0, t_w[15:14]} : {1'b0, t_w[14:12]};
  // ROM word addresses (gfx_layout.py): K tiles pixels 0-7 at +16, SRD tiles at +0
  wire [3:0]   bg_y    = bg_ly[3:0];
  wire         bg_half = sr ? t_j : !t_j;
  wire [21:0]  bg_addr = BG_BASE + {3'd0, bg_code, bg_half, bg_y, 2'b00};
  wire [21:0]  fx_addr = FIX_BASE + {7'd0, fx_code, fx_ly[2:0], 2'b00};
  // screen x of the word's first pixel; logical x = col*16 + j*8 (bg), col*8 (fix)
  wire [8:0]   bg_lx   = {bg_col, t_j, 3'd0};
  wire [8:0]   bg_x0   = r_flip ? (9'd255 + r_sx - bg_lx) : (bg_lx - r_sx);
  wire [7:0]   fx_x0   = r_flip ? 8'd255 - {fx_col, 3'd0} : {fx_col, 3'd0};
  wire [5:0]   t_last  = t_layer ? 6'd31 : 6'd16;
  wire         t_req   = t_st == T_ISS;

  // ---- sprite walker
  // Karnov (krn:31-125): 256 entries of 4 words, drawn in list order,
  // later entries over earlier (lastmisn) or last-to-first with the first
  // opaque pixel winning (gondo): in both the visible sprite pixel is the
  // one of the highest-numbered entry, so the walker runs 0 to 255 and the
  // line buffer keeps the last opaque write (with its behind flag).
  // srdarwin (v:159-205): 128 entries of 4 bytes, drawn 127 down to 0, first
  // opaque pixel wins: again the highest-numbered entry, walked 0 to 127.
  localparam logic [2:0] W_A0 = 3'd0, W_D0 = 3'd1, W_D1 = 3'd2, W_D2 = 3'd3, W_D3 = 3'd4,
                         W_POS = 3'd5, W_HIT = 3'd6, W_IDLE = 3'd7;
  logic [2:0]  w_st;
  logic [7:0]  w_e;
  logic        w_done;
  logic [15:0] w0, w1, w2;
  logic [10:0] w_ys, w_xs, w_ys2;  // signed screen positions (registered in W_POS)
  logic        w_fx, w_fy, w_two;
  logic [11:0] w_c0, w_c1;
  logic [3:0]  w_col;
  logic        w_bh;
  wire  [7:0]  w_last = sr ? 8'd127 : 8'd255;

  // Karnov position math on words 0-3 (w0..w2 registered, word 3 = spr_q in W_D3)
  wire         k_extra = w0[11];
  wire  [8:0]  k_yt    = w0[8:0] + 9'd16 + (k_extra ? 9'd16 : 9'd0);   // (y [+16] + 16) & 0x1ff
  wire  [8:0]  k_xt    = w2[8:0] + 9'd16;
  wire  [10:0] k_ys0   = 11'd256 - {2'd0, k_yt};
  wire  [10:0] k_xs0   = 11'd256 - {2'd0, k_xt};
  wire         k_fl    = KRN_FLIP && r_flip;
  wire  [10:0] k_ys    = k_fl ? (11'd240 - k_ys0 - (k_extra ? 11'd16 : 11'd0)) : k_ys0;
  wire  [10:0] k_xs    = k_fl ? (11'd240 - k_xs0) : k_xs0;
  wire         k_fx    = w1[2] ^ k_fl;
  wire         k_fy    = w1[1] ^ k_fl;
  wire  [11:0] k_spr   = k_extra ? {spr_q[11:1], 1'b0} : spr_q[11:0];
  wire  [11:0] k_c0    = (k_extra && k_fy) ? (k_spr | 12'd1) : k_spr;
  wire  [11:0] k_c1    = (k_extra && k_fy) ? k_spr : (k_spr | 12'd1);
  // srdarwin on bytes b0 = w0[15:8], b1 = w0[7:0], b2 = w1[15:8], b3 = w1[7:0]
  // (w1 = spr_q in W_D1)
  wire  [7:0]  s_b0    = w0[15:8];
  wire  [7:0]  s_b1    = w0[7:0];
  wire  [10:0] s_code  = {s_b1[7:5], spr_q[7:0]};
  wire  [10:0] s_sx0   = 11'd241 - {3'd0, spr_q[15:8]};
  wire  [10:0] s_sy    = r_flip ? (11'd240 - {3'd0, s_b0}) : {3'd0, s_b0};
  wire  [10:0] s_sx    = r_flip ? (11'd240 - s_sx0) : s_sx0;
  wire  [10:0] s_sy2   = r_flip ? (s_sy - 11'd16) : (s_sy + 11'd16);
  wire         s_skip  = s_code == 11'd0 || s_b0 == 8'hF8;

  // hit test on the registered positions (W_HIT)
  wire  [10:0] h_d0    = {3'd0, r_line} - w_ys;
  wire  [10:0] h_d1    = {3'd0, r_line} - w_ys2;
  // Karnov: part 1 is rows 16-31 of the same position; srdarwin: its own position
  wire         h_p0    = h_d0[10:4] == 7'd0;
  wire         h_p1    = w_two && (sr ? (h_d1[10:4] == 7'd0) : (h_d0[10:5] == 6'd0 && h_d0[4]));
  wire  [3:0]  h_r     = h_p0 ? h_d0[3:0] : (sr ? h_d1[3:0] : h_d0[3:0]);
  wire  [3:0]  h_row   = w_fy ? 4'd15 - h_r : h_r;
  wire  [11:0] h_code  = h_p0 ? w_c0 : w_c1;

  // ---- hit queue: {x[10:0], fx, code[11:0], row[3:0], colour[3:0], behind}
  logic        h_push, h_pop, h_empty, h_full;
  logic [32:0] h_d, h_q;
  /* verilator lint_off PINCONNECTEMPTY */
  d8_fifo #(.W(33), .DEPTH(16)) u_hits (
      .clk, .clr(!rst_n), .push(h_push), .d(h_d), .pop(h_pop), .q(h_q),
      .empty(h_empty), .full(h_full), .count());

  // ---- request tags: {layer[1:0], x0[10:0], dir, wide, fmt[1:0], attr[4:0]}
  logic        m_push, m_pop, m_empty, m_full;
  logic [21:0] m_d, m_q;
  d8_fifo #(.W(22), .DEPTH(8)) u_tags (
      .clk, .clr(!rst_n), .push(m_push), .d(m_d), .pop(m_pop), .q(m_q),
      .empty(m_empty), .full(m_full), .count());

  // ---- returned words
  logic        d_pop, d_empty;
  logic [31:0] d_q;
  d8_fifo #(.W(32), .DEPTH(8)) u_ret (
      .clk, .clr(!rst_n), .push(i_rom_rv), .d(i_rom_data), .pop(d_pop), .q(d_q),
      .empty(d_empty), .full(), .count());
  /* verilator lint_on PINCONNECTEMPTY */

  // ---- sprite line buffer clear (the pass's half, before any sprite pixel)
  logic [8:0]  clr_i;
  wire         clr_done = clr_i[8];

  // ---- sprite fetcher: two words (pixels 0-7, 8-15) per hit
  logic        f_j;
  wire  [10:0] f_x     = h_q[32:22];
  wire         f_fx    = h_q[21];
  wire  [11:0] f_code  = h_q[20:9];
  wire  [3:0]  f_row   = h_q[8:5];
  wire  [4:0]  f_attr  = h_q[4:0];               // {colour, behind}
  // both sprite layouts keep pixels 0-7 at +16 (gfx_layout.py)
  wire  [21:0] f_addr  = SPR_BASE + {3'd0, (sr ? {1'b0, f_code[10:0]} : f_code), !f_j, f_row, 2'b00};
  wire  [10:0] f_x0    = f_x + (f_fx ? (f_j ? 11'd7 : 11'd15) : (f_j ? 11'd8 : 11'd0));
  wire         f_req   = t_done && clr_done && !h_empty && busy;

  localparam logic [1:0] FMT_K4 = 2'd0, FMT_P3 = 2'd1, FMT_SRT = 2'd2, FMT_SRC = 2'd3;
  wire  [1:0]  bg_fmt  = sr ? FMT_SRT : FMT_K4;
  wire  [1:0]  fx_fmt  = sr ? FMT_SRC : FMT_P3;
  wire  [1:0]  sp_fmt  = sr ? FMT_P3 : FMT_K4;

  assign o_rom_req  = (t_req || f_req) && !m_full;
  assign o_rom_addr = t_req ? (t_layer ? fx_addr : bg_addr) : f_addr;
  wire   accept     = o_rom_req && i_rom_gnt;
  assign m_push     = accept;
  assign m_d        = t_req ? (t_layer ? {2'd1, 3'd0, fx_x0, r_flip, 1'b0, fx_fmt, fx_attr, 1'b0}
                                       : {2'd0, 2'd0, bg_x0, r_flip, 1'b1, bg_fmt, bg_attr, 1'b0})
                            : {2'd2, f_x0, f_fx, 1'b0, sp_fmt, f_attr};
  assign h_pop      = accept && !t_req && f_j;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      busy <= 1'b0;
      pend <= 1'b0;
      t_st <= T_IDLE;
      t_done <= 1'b1;
      w_st <= W_IDLE;
      w_done <= 1'b1;
      f_j <= 1'b0;
      clr_i <= 9'h100;
      cyc <= '0;
      maxcyc <= '0;
      overruns <= '0;
    end else begin
      // ---- line start / overrun bookkeeping
      if (want_line && busy) begin
        overruns <= overruns + 16'd1;
        pend <= 1'b1;
        pend_line <= next_line;
      end else if (go) pend <= 1'b0;

      if (go) begin
        busy <= 1'b1;
        r_line <= go_line[7:0];
        r_flip <= v_flip;
        r_sx <= v_sx;
        r_sy <= v_sy;
        t_st <= T_ADDR;
        t_layer <= 1'b0;
        t_k <= '0;
        t_j <= 1'b0;
        t_done <= 1'b0;
        w_st <= W_A0;
        w_e <= '0;
        w_done <= 1'b0;
        f_j <= 1'b0;
        clr_i <= '0;
        cyc <= '0;
      end else if (busy) begin
        cyc <= cyc + 16'd1;
        if (t_done && w_done && h_empty && m_empty && d_empty && clr_done) begin
          busy <= 1'b0;
          if (cyc > maxcyc) maxcyc <= cyc;
        end
      end

      if (!go && !clr_done) clr_i <= clr_i + 9'd1;

      // ---- tile issuer: tile RAM read, then 2 (bg) or 1 (fix) requests
      case (t_st)
        T_ADDR: begin
          t_lane <= fx_tile[0];
          t_st <= T_WAIT;
        end
        T_WAIT: begin
          t_w <= t_layer ? fix_q : bg_q;
          t_st <= T_ISS;
        end
        T_ISS: if (accept) begin
          if (!t_layer && !t_j) t_j <= 1'b1;
          else begin
            t_j <= 1'b0;
            if (t_k == t_last) begin
              t_k <= '0;
              if (t_layer) begin
                t_st <= T_IDLE;
                t_done <= 1'b1;
              end else begin
                t_layer <= 1'b1;
                t_st <= T_ADDR;
              end
            end else begin
              t_k <= t_k + 6'd1;
              t_st <= T_ADDR;
            end
          end
        end
        default: ;
      endcase

      // ---- sprite walker: each state presents the next word address; the
      // word arrives on spr_q in the following state
      if (!go) begin
        case (w_st)
          W_A0: w_st <= W_D0;
          W_D0: begin                               // spr_q = word 0
            w0 <= spr_q;
            if (!sr && !spr_q[15]) begin            // Karnov: not enabled (krn:40)
              if (w_e == w_last) w_st <= W_IDLE;
              else begin
                w_e <= w_e + 8'd1;
                w_st <= W_A0;
              end
            end else w_st <= W_D1;
          end
          W_D1: begin                               // spr_q = word 1
            w1 <= spr_q;
            if (sr) begin
              if (s_skip) begin                     // code 0 or y 0xf8 (v:172-177)
                if (w_e == w_last) w_st <= W_IDLE;
                else begin
                  w_e <= w_e + 8'd1;
                  w_st <= W_A0;
                end
              end else begin
                w_ys <= s_sy;
                w_ys2 <= s_sy2;
                w_xs <= s_sx;
                w_fx <= s_b1[2] ^ r_flip;
                w_fy <= r_flip;
                w_two <= s_b1[4];
                w_c0 <= {1'b0, s_code};
                w_c1 <= {1'b0, s_code + 11'd1};     // code + 1 wraps at 2,048 elements
                w_col <= {1'b0, s_b1[3], s_b1[1:0]};
                w_bh <= {s_b1[3], s_b1[1:0]} == 3'd0;  // colour 0 behind priority 2
                w_st <= W_HIT;
              end
            end else if (!spr_q[0]) begin           // Karnov: word 1 bit 0 clear (krn:58)
              if (w_e == w_last) w_st <= W_IDLE;
              else begin
                w_e <= w_e + 8'd1;
                w_st <= W_A0;
              end
            end else w_st <= W_D2;
          end
          W_D2: begin                               // spr_q = word 2
            w2 <= spr_q;
            w_st <= W_D3;
          end
          W_D3: begin                               // spr_q = word 3: positions
            w_ys <= k_ys;
            w_ys2 <= k_ys;
            w_xs <= k_xs;
            w_fx <= k_fx;
            w_fy <= k_fy;
            w_two <= k_extra;
            w_c0 <= k_c0;
            w_c1 <= k_c1;
            w_col <= spr_q[15:12];
            w_bh <= go_m && spr_q[15];              // gondo_colpri_cb: colour bit 3 (v:462-467)
            w_st <= W_HIT;
          end
          W_HIT: if (!(h_p0 || h_p1) || !h_full) begin
            if (w_e == w_last) w_st <= W_IDLE;
            else begin
              w_e <= w_e + 8'd1;
              w_st <= W_A0;
            end
          end
          default: ;
        endcase
        if (w_st == W_IDLE) w_done <= 1'b1;
      end

      // ---- fetcher word counter
      if (accept && !t_req) f_j <= !f_j;
    end
  end

  // word address on the sprite buffer port for the walker's next read
  always_comb begin
    case (w_st)
      W_A0:   spr_va = sr ? {2'd0, w_e[6:0], 1'b0} : {w_e, 2'd0};
      W_D0:   spr_va = sr ? {2'd0, w_e[6:0], 1'b1} : {w_e, 2'd1};
      W_D1:   spr_va = {w_e, 2'd2};
      W_D2:   spr_va = {w_e, 2'd3};
      default: spr_va = {w_e, 2'd0};
    endcase
  end
  // Karnov entry e = words 4e..4e+3; srdarwin entry e = bytes 4e..4e+3 =
  // words 2e ({b0, b1}) and 2e+1 ({b2, b3})
  assign h_push = !go && w_st == W_HIT && (h_p0 || h_p1) && !h_full && busy;
  assign h_d    = {w_xs, w_fx, h_code, h_row, w_col, w_bh};

  // ---- writer: one pixel per clock from the returned words
  logic [2:0]  wb;
  wire  [1:0]  w_lay  = m_q[21:20];
  wire  [10:0] w_x0   = m_q[19:9];
  wire         w_dir  = m_q[8];
  wire         w_wide = m_q[7];
  wire  [1:0]  w_fmt  = m_q[6:5];
  wire  [4:0]  w_at   = m_q[4:0];
  // pixel decode (gfx_layout.decode_word)
  logic [3:0]  pix;
  always_comb begin
    logic [7:0] a, c;
    logic [1:0] xx;
    xx = wb[1:0];
    a = wb[2] ? d_q[15:8] : d_q[31:24];
    c = wb[2] ? d_q[7:0]  : d_q[23:16];
    case (w_fmt)
      FMT_K4:  pix = {d_q[3'd7 - wb], d_q[5'd15 - {2'd0, wb}], d_q[5'd23 - {2'd0, wb}], d_q[5'd31 - {2'd0, wb}]};
      FMT_P3:  pix = {1'b0, d_q[5'd15 - {2'd0, wb}], d_q[5'd23 - {2'd0, wb}], d_q[5'd31 - {2'd0, wb}]};
      FMT_SRT: pix = {a[3'd7 - {1'b0, xx}], a[3'd3 - {1'b0, xx}], c[3'd7 - {1'b0, xx}], c[3'd3 - {1'b0, xx}]};
      default: begin                                // FMT_SRC: pixels 0-3 lane 0, 4-7 lane 1
        a = wb[2] ? d_q[23:16] : d_q[31:24];
        pix = {2'd0, a[3'd7 - {1'b0, xx}], a[3'd3 - {1'b0, xx}]};
      end
    endcase
  end
  wire         is_sp  = w_lay == 2'd2;
  wire  [10:0] wx_s   = w_dir ? w_x0 - {8'd0, wb} : w_x0 + {8'd0, wb};
  wire  [8:0]  wx_t0  = w_dir ? w_x0[8:0] - {6'd0, wb} : w_x0[8:0] + {6'd0, wb};
  wire  [8:0]  wx_t   = w_wide ? wx_t0 : {1'b0, wx_t0[7:0]};
  wire         wvis   = is_sp ? (wx_s[10:8] == 3'd0 && pix != 4'd0) : !wx_t[8];
  wire         wact   = !d_empty && !m_empty;
  wire  [7:0]  wx     = is_sp ? wx_s[7:0] : wx_t[7:0];
  wire  [8:0]  lb_wa  = {r_line[0], wx};
  wire         wr_en  = wact && wvis;
  assign d_pop = wact && wb == 3'd7;
  assign m_pop = d_pop;
  always_ff @(posedge clk) begin
    if (!rst_n) wb <= '0;
    else if (wact) wb <= wb + 3'd1;
  end

  assign o_dbg_overruns = overruns;
  assign o_dbg_maxcyc   = maxcyc;

  // ---- line buffers: port A written by the writer, port B read by scan-out
  // bg {attr, pen}, fix {attr, pen}, sprites {behind, colour, pen}
  wire  [8:0]  lb_ra = {vcnt[0], hcnt[7:0]};
  logic [15:0] lbq_bg, lbq_fx, lbq_sp;
  /* verilator lint_off PINCONNECTEMPTY */
  d8_dpram #(.AW(9), .DW(16)) u_lb_bg (
      .clk, .addr_a(lb_wa), .d_a({8'd0, w_at[4:1], pix}), .we_a(wr_en && w_lay == 2'd0), .be_a(2'b11),
      .q_a(), .addr_b(lb_ra), .q_b(lbq_bg));
  d8_dpram #(.AW(9), .DW(16)) u_lb_fx (
      .clk, .addr_a(lb_wa), .d_a({8'd0, w_at[4:1], pix}), .we_a(wr_en && w_lay == 2'd1), .be_a(2'b11),
      .q_a(), .addr_b(lb_ra), .q_b(lbq_fx));
  d8_dpram #(.AW(9), .DW(16)) u_lb_sp (
      .clk, .addr_a(clr_done ? lb_wa : {r_line[0], clr_i[7:0]}),
      .d_a(clr_done ? {7'd0, w_at[0], w_at[4:1], pix} : 16'd0),
      .we_a(clr_done ? (wr_en && is_sp) : busy), .be_a(2'b11),
      .q_a(), .addr_b(lb_ra), .q_b(lbq_sp));
  /* verilator lint_on PINCONNECTEMPTY */

  // ================================================================ mixer
  // lastmisn (v:334-345): bg opaque, sprites over it, fix (pen 0
  // transparent) on top. gondo (v:517-524): bg pens 8-15 are layer 0
  // (priority 2); a sprite with colour bit 3 is behind them. srdarwin
  // (v:412-460): bg group 3 all pens and groups 1-2 pens 8-15 are layer 0;
  // a colour 0 sprite is behind them. Palette index (spec 6): fix col*8+pen
  // (srdarwin 128+pen), sprites 256+colour*16+pen (srdarwin 64+colour*8+pen),
  // bg 768+colour*16+pen (srdarwin group*16+pen).
  logic [9:0] mx;
  always_comb begin
    logic [3:0] bgp, bga, fxp, fxa, spp, spa;
    logic       spb, l0;
    bgp = lbq_bg[3:0]; bga = lbq_bg[7:4];
    fxp = lbq_fx[3:0]; fxa = lbq_fx[7:4];
    spp = lbq_sp[3:0]; spa = lbq_sp[7:4]; spb = lbq_sp[8];
    l0 = sr ? (bga[1:0] == 2'd3 || (bga[1:0] != 2'd0 && bgp[3])) : (go_m && bgp[3]);
    if (fxp != 4'd0)
      mx = sr ? {8'b00100000, fxp[1:0]} : {4'd0, fxa[2:0], fxp[2:0]};
    else if (spp != 4'd0 && !(spb && l0))
      mx = sr ? {4'b0001, spa[2:0], spp[2:0]} : {2'b01, spa, spp};
    else
      mx = sr ? {4'b0000, bga[1:0], bgp} : {2'b11, bga, bgp};
  end

  // ================================================================ scan-out
  // Phase within the pixel (16 clocks): 0 line buffers addressed by the
  // counters, 1 mixer result registered, 2 palette addressed, 3 entry
  // registered; the colour is registered at the next pixel enable (one
  // pixel of pipeline delay on every output).
  logic [3:0]  ph;
  logic [9:0]  ma;
  logic [15:0] col;
  always_ff @(posedge clk) begin
    if (ce_pix) ph <= 4'd0;
    else if (ph != 4'd15) ph <= ph + 4'd1;
  end
  assign pal_va = ma;
  always_ff @(posedge clk) begin
    if (ph == 4'd1) ma <= mx;
    if (ph == 4'd3) col <= pal_q;
  end
  // DECO RM-C3 (decrmc3.cpp:214-224): R = bits 0-3, G = 4-7, B = ext 0-3,
  // each bit weighted 0x0e, 0x1f, 0x43, 0x8f
  function automatic [7:0] wt(input [3:0] v);
    wt = (v[0] ? 8'h0e : 8'h00) + (v[1] ? 8'h1f : 8'h00) + (v[2] ? 8'h43 : 8'h00) + (v[3] ? 8'h8f : 8'h00);
  endfunction

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      o_de <= 1'b0;
      o_hblank <= 1'b1;
      o_vblank <= 1'b1;
      o_hs <= 1'b0;
      o_vs <= 1'b0;
    end else if (ce_pix) begin
      o_de     <= hcnt < 9'(H_ACT) && vcnt >= 9'(V_VIS0) && vcnt <= 9'(V_VIS1);
      o_hblank <= hcnt >= 9'(H_ACT);
      o_vblank <= vcnt < 9'(V_VIS0) || vcnt > 9'(V_VIS1);
      o_hs     <= hcnt >= 9'(HS_START) && hcnt < 9'(HS_END);
      o_vs     <= vcnt >= 9'(VS_START) && vcnt < 9'(VS_START + 3);
      o_r <= wt(col[3:0]);
      o_g <= wt(col[7:4]);
      o_b <= wt(col[11:8]);
      o_dbg_pen <= ma;
    end
  end

endmodule
