// DEC8 main system for Last Mission, Gondomania and SRD (PLAN M2).
//
// Reference: MAME 0.288 dataeast/dec8.cpp (and dec8_v.cpp, cpu/mcs51,
// machine/input_merger) vendored in reference/mame/v0288/; "spec N" =
// docs/dec8_system_spec.md, "dec8:L" = dec8.cpp line numbers.
//
// Contents
//   - main 6809 (lastmisn, srdarwin: MC6809E at 1.5 MHz; gondo: HD6309E at
//     3 MHz run as a 6809, which is the 6309's emulation mode the program
//     never leaves, m0_findings 2, R4), lastmisn's second 6809 (sub);
//     cycle-accurate mc6809i cores (rtl/vendor/mc6809i)
//   - i8751 MCU (d8_mcu: jt8051) with the per-machine port glue of
//     dec8:732-790 and its interrupt lines
//   - memory maps (dec8:301-350, 451-472, 562-592), work RAM, bank and
//     control registers, inputs, interrupt registers and gates
//   - d8_video (M1) with the CPU side decoded here
//   - the sound latch is written here; the sound board is d8_snd (M3)
//
// Clocking (96 MHz system clock, one clock domain):
//   CPU bus cycle = P clocks: P = 64 (1.5 MHz E) or 32 (gondo 3 MHz E).
//   ph = 0 .. P-1; mc6809i takes cen_E at ph = P-1 (falling E: the state
//   advances and a read cycle's data is taken) and cen_Q at ph = 3P/4 - 1
//   (falling Q: interrupt lines sampled), the 6809E's quadrature clocks.
//   A bus cycle starts at ph = 0 with the address the state set at cen_E.
//   Program ROM (SDRAM): request at ph = 1, data held in a latch until
//   cen_E; `o_dbg_prom_late` counts a fetch whose data was not there by
//   ph = P-2 (it would have needed a wait state; must stay 0).
//   RAM and I/O: the main CPU's access at ph = SLOT_M, the sub CPU's at
//   SLOT_S (lastmisn shares the video, work RAM and I/O between the two
//   CPUs; MAME runs them instruction by instruction with no contention),
//   writes as a single strobe at the slot, reads latched 3 clocks later.
//   MCU: cen every 12 clocks (8 MHz oscillator, dec8:1997).
//   Pause holds the CPU phase counters, the MCU enable and the interrupt
//   timers; video keeps running.

module d8_sys #(
    parameter bit KRN_FLIP = 1'b0,
    parameter bit LATCH    = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [1:0]  i_machine,       // 0 lastmisn, 1 gondo, 2 srdarwin
    input  logic        i_srdb,          // srdarwinb (no MCU, dec8:586-592)
    input  logic        i_pause,

    // inputs as MAME's ports (active low), DIPs, rotary positions (gondo)
    input  logic [7:0]  i_in0,
    input  logic [7:0]  i_in1,
    input  logic [7:0]  i_in2,
    input  logic [7:0]  i_in3,
    input  logic [7:0]  i_coin,
    input  logic [7:0]  i_dsw0,
    input  logic [7:0]  i_dsw1,
    input  logic [3:0]  i_an0,           // 0-11
    input  logic [3:0]  i_an1,

    // program ROM (SDRAM image layout, tools/build_regions.py SDRAM_SLOTS)
    output logic        o_prom_req,
    output logic [20:0] o_prom_addr,
    input  logic [7:0]  i_prom_data,
    input  logic        i_prom_ok,
    output logic        o_srom_req,      // lastmisn sub CPU
    output logic [20:0] o_srom_addr,
    input  logic [7:0]  i_srom_data,
    input  logic        i_srom_ok,

    // MCU program ROM load (before reset is released)
    input  logic        i_mcu_we,
    input  logic [11:0] i_mcu_addr,
    input  logic [7:0]  i_mcu_din,

    // graphics ROM port (d8_video)
    output logic        o_rom_req,
    output logic [21:0] o_rom_addr,
    input  logic        i_rom_gnt,
    input  logic        i_rom_rv,
    input  logic [31:0] i_rom_data,

    // sound latch (also inside: d8_snd)
    output logic        o_snd_wr,
    output logic [7:0]  o_snd_data,

    // sound board (M3, d8_snd): ROM load (8000-FFFF, before reset is
    // released) and audio
    input  logic        i_snd_we,
    input  logic [14:0] i_snd_addr,
    input  logic [7:0]  i_snd_din,
    output logic signed [15:0] o_fm,
    output logic        [9:0]  o_ssg,
    output logic signed [15:0] o_opl,
    output logic signed [15:0] o_audio,
    output logic [15:0] o_dbg_snd_unmapped,

    // video
    output logic [7:0]  o_r,
    output logic [7:0]  o_g,
    output logic [7:0]  o_b,
    output logic        o_de,
    output logic        o_hblank,
    output logic        o_vblank,
    output logic        o_hs,
    output logic        o_vs,
    output logic        o_vbl,           // one clock at the start of line 248
    output logic        o_ce_pix,
    output logic [9:0]  o_pen,

    // gate counters
    output logic [15:0] o_dbg_overruns,
    output logic [15:0] o_dbg_maxcyc,
    output logic [7:0]  o_dbg_verr,
    output logic [15:0] o_dbg_prom_late,
    output logic [15:0] o_dbg_unmapped,
    output logic [15:0] o_dbg_xacc
);

  wire lm = i_machine == 2'd0;
  wire go = i_machine == 2'd1;
  wire sr = i_machine == 2'd2;
  wire has_mcu = !(sr && i_srdb);

  // ================================================================ clocks
  wire [6:0] P = go ? 7'd32 : 7'd64;
  logic [6:0] ph /* verilator public_flat_rd */;
  logic [3:0] pxc;
  logic [3:0] mcnt;
  wire run = !i_pause;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      ph <= '0; pxc <= '0; mcnt <= '0;
    end else begin
      pxc <= pxc + 4'd1;
      if (run) begin
        ph <= (ph == P - 7'd1) ? 7'd0 : ph + 7'd1;
        mcnt <= (mcnt == 4'd11) ? 4'd0 : mcnt + 4'd1;
      end
    end
  end
  wire ce_pix = pxc == 4'd15;
  wire cen_E /* verilator public_flat_rd */ = run && ph == P - 7'd1;
  wire cen_Q = run && ph == (P - (P >> 2) - 7'd1);
  wire mcu_cen = run && mcnt == 4'd11;
  localparam logic [6:0] SLOT_M = 7'd12, SLOT_S = 7'd20;
  wire at_m /* verilator public_flat_rd */ = run && ph == SLOT_M;
  wire at_s /* verilator public_flat_rd */ = run && lm && ph == SLOT_S;

  // ================================================================ CPUs
  logic [15:0] m_a /* verilator public_flat_rd */, s_a /* verilator public_flat_rd */;
  logic [7:0]  m_do /* verilator public_flat_rd */, s_do /* verilator public_flat_rd */, m_di /* verilator public_flat_rd */, s_di /* verilator public_flat_rd */;
  logic        m_rnw /* verilator public_flat_rd */, s_rnw /* verilator public_flat_rd */;
  logic        m_irqn, m_firqn, m_nmin, s_irqn, s_firqn;
  logic        s_hold;               // lastmisn control bit 7 clear: sub held in reset
  logic        m_op /* verilator public_flat_rd */, s_op /* verilator public_flat_rd */;   // opcode fetch cycle (trace)
  /* verilator lint_off PINCONNECTEMPTY */
  mc6809i u_main (
      .D(m_di), .DOut(m_do), .ADDR(m_a), .RnW(m_rnw), .clk, .cen_E, .cen_Q,
      .BS(), .BA(), .nIRQ(m_irqn), .nFIRQ(m_firqn), .nNMI(m_nmin), .AVMA(), .BUSY(), .LIC(),
      .nHALT(1'b1), .nRESET(rst_n), .nDMABREQ(1'b1), .OP(m_op), .RegData());
  mc6809i u_sub (
      .D(s_di), .DOut(s_do), .ADDR(s_a), .RnW(s_rnw), .clk, .cen_E, .cen_Q,
      .BS(), .BA(), .nIRQ(s_irqn), .nFIRQ(s_firqn), .nNMI(1'b1), .AVMA(), .BUSY(), .LIC(),
      .nHALT(1'b1), .nRESET(rst_n && lm && !s_hold), .nDMABREQ(1'b1), .OP(s_op), .RegData());
  /* verilator lint_on PINCONNECTEMPTY */

  // ================================================================ decode
  // per-CPU decode of the cycle's address (valid from ph = 0)
  typedef enum logic [4:0] {
    R_NONE, R_ROM, R_RAM, R_PAL, R_PALX, R_FIX, R_BG, R_SPR, R_IN0, R_IN1, R_IN2, R_IN3,
    R_DSW0, R_DSW1, R_MCUHI, R_MCULO, R_COIN, R_P1ROT0, R_P1ROT1, R_P2ROT0, R_P2ROT1, R_ZERO
  } rsel_t;
  typedef enum logic [4:0] {
    W_NONE, W_RAM, W_PAL, W_PALX, W_FIX, W_BG, W_SPR, W_SUBIRQ_OFF, W_MAINIRQ_OFF, W_FIRQ_OFF,
    W_MAINIRQ_ON, W_SUBIRQ_ON, W_SPRCOPY, W_FLIP, W_SCRX, W_SCRY, W_SOUND, W_LMCTRL, W_MCUHI,
    W_MCULO, W_GOSCR, W_GOBANK, W_SRCTRL0, W_SRCTRL1, W_ROM
  } wsel_t;

  typedef struct packed {
    rsel_t      r;
    wsel_t      w;
    logic [12:0] ram;     // work RAM byte address
    logic [10:0] vaddr;   // video RAM byte address / palette entry
    logic       mapped;   // MAME maps this address (for the unmapped counter)
  } dec_t;

  function automatic dec_t decode(input logic [15:0] a, input logic is_sub,
                                  input logic m_lm, input logic m_go, input logic m_sr, input logic srdb);
    dec_t d;
    d.r = R_ZERO; d.w = W_NONE; d.ram = '0; d.vaddr = '0; d.mapped = 1'b1;
    if (m_lm) begin
      // lastmisn_map / lastmisn_sub_map (dec8:301-350)
      if (a < 16'h1000) begin d.r = R_RAM; d.w = W_RAM; d.ram = {1'b0, a[11:0]}; end
      else if (a < 16'h1400) begin d.r = R_PAL; d.w = W_PAL; d.vaddr = {1'b0, a[9:0]}; end
      else if (a < 16'h1800) begin d.r = R_PALX; d.w = W_PALX; d.vaddr = {1'b0, a[9:0]}; end
      else if (a < 16'h2000) begin
        case (a)
          16'h1800: begin d.r = R_IN0;  d.w = W_SUBIRQ_OFF; end
          16'h1801: begin d.r = R_IN1;  d.w = W_MAINIRQ_OFF; end
          16'h1802: begin d.r = R_IN2;  d.w = W_FIRQ_OFF; end
          16'h1803: begin d.r = R_DSW0; d.w = W_MAINIRQ_ON; end
          16'h1804: begin d.r = R_DSW1; d.w = W_SUBIRQ_ON; end
          16'h1805: begin d.w = W_SPRCOPY; d.mapped = 1'b1; end
          16'h1806: d.r = R_MCUHI;
          16'h1807: begin d.r = R_MCULO; d.w = W_FLIP; end
          16'h1809: begin if (!is_sub) d.w = W_SCRX; else d.mapped = 1'b0; end
          16'h180b: begin if (!is_sub) d.w = W_SCRY; else d.mapped = 1'b0; end
          16'h180c: d.w = W_SOUND;
          16'h180d: begin if (!is_sub) d.w = W_LMCTRL; else d.mapped = 1'b0; end
          16'h180e: d.w = W_MCUHI;
          16'h180f: d.w = W_MCULO;
          default:  d.mapped = 1'b0;
        endcase
      end
      else if (a < 16'h2800) begin d.r = R_FIX; d.w = W_FIX; d.vaddr = a[10:0]; end
      else if (a < 16'h3000) begin d.r = is_sub ? R_ZERO : R_SPR; d.w = W_SPR; d.vaddr = a[10:0]; end
      else if (a < 16'h3800) begin d.r = R_RAM; d.w = W_RAM; d.ram = {2'b10, a[10:0]}; end
      else if (a < 16'h4000) begin d.r = R_BG; d.w = W_BG; d.vaddr = a[10:0]; end
      else begin d.r = R_ROM; d.w = W_ROM; end
    end else if (m_go) begin
      // gondo_map (dec8:451-472)
      if (a < 16'h1800) begin d.r = R_RAM; d.w = W_RAM; d.ram = a[12:0]; end
      else if (a < 16'h2000) begin d.r = R_FIX; d.w = W_FIX; d.vaddr = a[10:0]; end
      else if (a < 16'h2800) begin d.r = R_BG; d.w = W_BG; d.vaddr = a[10:0]; end
      else if (a < 16'h2c00) begin d.r = R_PAL; d.w = W_PAL; d.vaddr = {1'b0, a[9:0]}; end
      else if (a < 16'h3000) begin d.r = R_PALX; d.w = W_PALX; d.vaddr = {1'b0, a[9:0]}; end
      else if (a < 16'h3800) begin d.r = R_SPR; d.w = W_SPR; d.vaddr = a[10:0]; end
      else if (a < 16'h4000) begin
        if (a == 16'h3800) d.r = R_DSW0;
        else if (a == 16'h3801) d.r = R_DSW1;
        else if (a == 16'h380a) d.r = R_P1ROT0;
        else if (a == 16'h380b) d.r = R_P1ROT1;
        else if (a == 16'h380c) d.r = R_P2ROT0;
        else if (a == 16'h380d) d.r = R_P2ROT1;
        else if (a == 16'h380e) d.r = R_IN3;
        else if (a == 16'h380f) d.r = R_IN2;
        else if (a == 16'h3810) d.w = W_SOUND;
        else if (a >= 16'h3818 && a <= 16'h382f) d.w = W_GOSCR;
        else if (a == 16'h3830) d.w = W_GOBANK;
        else if (a == 16'h3838) d.r = R_MCUHI;
        else if (a == 16'h3839) d.r = R_MCULO;
        else if (a == 16'h383a) d.w = W_MCUHI;
        else if (a == 16'h383b) d.w = W_MCULO;
        else d.mapped = 1'b0;
      end
      else begin d.r = R_ROM; d.w = W_ROM; end
    end else begin
      // srdarwin main_map / srdarwinb_map (dec8:562-592)
      if (a < 16'h0600) begin d.r = R_RAM; d.w = W_RAM; d.ram = {2'b00, a[10:0]}; end
      else if (a < 16'h0800) begin d.r = R_SPR; d.w = W_SPR; d.vaddr = {2'b00, a[8:0]}; end
      else if (a < 16'h1000) begin d.r = R_FIX; d.w = W_FIX; d.vaddr = a[10:0]; end
      else if (a < 16'h1400) begin d.r = R_RAM; d.w = W_RAM; d.ram = {3'b110, a[9:0]}; end
      else if (a < 16'h1800) begin d.r = R_BG; d.w = W_BG; d.vaddr = {1'b0, a[9:0]}; end
      else if (a < 16'h2000) begin
        if (a == 16'h1800) d.w = srdb ? W_NONE : W_MCUHI;
        else if (a == 16'h1801) d.w = srdb ? W_NONE : W_MCULO;
        else if (a == 16'h1803) d.w = W_NONE;
        else if (a == 16'h1804) d.w = W_SPRCOPY;
        else if (a == 16'h1805) d.w = W_SRCTRL0;
        else if (a == 16'h1806) d.w = W_SRCTRL1;
        else d.mapped = 1'b0;
      end
      else if (a < 16'h2800) begin
        if (a == 16'h2000) begin d.r = srdb ? R_ZERO : R_MCUHI; d.w = W_SOUND; end
        else if (a == 16'h2001) begin d.r = srdb ? R_COIN : R_MCULO; d.w = W_FLIP; end
        else d.mapped = 1'b0;
      end
      else if (a >= 16'h2800 && a <= 16'h288f) begin d.r = R_ZERO; d.w = W_PAL; d.vaddr = {3'd0, a[7:0]}; end
      else if (a >= 16'h3000 && a <= 16'h308f) begin d.r = R_ZERO; d.w = W_PALX; d.vaddr = {3'd0, a[7:0]}; end
      else if (a == 16'h3800) d.r = R_DSW0;
      else if (a == 16'h3801) d.r = R_IN0;
      else if (a == 16'h3802) d.r = R_IN1;
      else if (a == 16'h3803) d.r = R_DSW1;
      else if (a < 16'h4000) d.mapped = 1'b0;
      else begin d.r = R_ROM; d.w = W_ROM; end
    end
    return d;
  endfunction

  dec_t md, sd;
  always_comb md = decode(m_a, 1'b0, lm, go, sr, i_srdb);
  always_comb sd = decode(s_a, 1'b1, lm, go, sr, i_srdb);

  // ================================================================ program ROM
  logic [3:0] bank /* verilator public_flat_rd */;   // mainbank entry
  // SDRAM byte address (build_regions.py SDRAM_SLOTS)
  wire [20:0] m_rom_addr = m_a[15] ? {5'd0, m_a} : (21'h010000 + {3'd0, bank, m_a[13:0]});
  wire [20:0] s_rom_addr = 21'h050000 + {5'd0, s_a};
  logic [7:0] m_rom_q, s_rom_q;
  logic       m_rom_have, s_rom_have;
  logic [15:0] prom_late;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      o_prom_req <= 1'b0; o_srom_req <= 1'b0; prom_late <= '0;
      m_rom_have <= 1'b0; s_rom_have <= 1'b0;
    end else begin
      if (run && ph == 7'd1) begin
        o_prom_req <= md.r == R_ROM && m_rnw;
        o_prom_addr <= m_rom_addr;
        m_rom_have <= 1'b0;
        o_srom_req <= lm && sd.r == R_ROM && s_rnw;
        o_srom_addr <= s_rom_addr;
        s_rom_have <= 1'b0;
      end
      if (o_prom_req && i_prom_ok) begin
        o_prom_req <= 1'b0; m_rom_q <= i_prom_data; m_rom_have <= 1'b1;
      end
      if (o_srom_req && i_srom_ok) begin
        o_srom_req <= 1'b0; s_rom_q <= i_srom_data; s_rom_have <= 1'b1;
      end
      if (run && ph == P - 7'd2 && ((o_prom_req && !(i_prom_ok)) || (o_srom_req && !(i_srom_ok))) &&
          prom_late != 16'hFFFF)
        prom_late <= prom_late + 16'd1;
    end
  end
  assign o_dbg_prom_late = prom_late;

  // ================================================================ work RAM
  // 8 KB: lastmisn share1 0x0000 (4 KB) + share2 0x1000 (2 KB); gondo 6 KB;
  // srdarwin 0x0000-0x05ff and 0x1000-0x13ff (at 0x1800 here)
  logic [7:0] wram [0:8191] /* verilator public_flat_rd */;
  logic [12:0] wr_a;
  logic [7:0]  wr_d, wr_q;
  logic        wr_we;
  always_ff @(posedge clk) begin
    if (wr_we) wram[wr_a] <= wr_d;
    wr_q <= wram[wr_a];
  end

  // ================================================================ registers
  logic [15:0] mcu_value, mcu_return;
  logic [7:0]  p0_ext, p1_ext, p0_force, mcu_p2_prev;
  logic        m_irq /* verilator public_flat_rd */, m_firq /* verilator public_flat_rd */, s_irq /* verilator public_flat_rd */, s_firq /* verilator public_flat_rd */;
  logic        secclr, nmi_en, nmi_en_d, strobe;
  logic [7:0]  bank_data;
  logic [5:0]  nmi_dly;
  logic        int0 /* verilator public_flat_rd */, int1 /* verilator public_flat_rd */;
  logic [8:0]  int1_tmr;
  logic        coin_state;
  logic [15:0] unmapped;

  // video CPU port (time-multiplexed main/sub)
  logic [10:0] v_addr;
  logic [7:0]  v_din;
  logic        v_pal_we, v_palx_we, v_fix_we, v_bg_we, v_spr_we, v_spr_copy, v_scr_we, v_flip_we;
  logic [1:0]  v_scr_sel;
  logic [7:0]  v_pal_q, v_palx_q, v_fix_q, v_bg_q, v_spr_q;
  logic        vblank_l;              // MAME screen vblank: lines 248-271 and 0-7
  logic        lm_scr2_pending;       // lastmisn control: second scroll write
  logic [7:0]  lm_scr2_val;
  logic        go_scr2_pending;
  logic [7:0]  go_scr2_val;

  // read data latches
  logic [7:0] m_rd, s_rd;
  rsel_t      m_rs, s_rs;

  // the access being serviced this clock
  wire        acc_m = at_m;
  wire        acc_s = at_s;
  wire        acc   = acc_m || acc_s;
  dec_t       ad;
  logic [7:0] adout;
  logic       arnw;
  always_comb begin
    ad    = acc_s ? sd : md;
    adout = acc_s ? s_do : m_do;
    arnw  = acc_s ? s_rnw : m_rnw;
  end
  wire do_w = acc && !arnw;

  // gondo player_io_r (dec8:115-129): one-hot rotary position
  wire [11:0] rot0 = 12'd1 << i_an0;
  wire [11:0] rot1 = 12'd1 << i_an1;

  function automatic logic [7:0] port_value(input rsel_t r);
    case (r)
      R_IN0:   return i_in0;
      R_IN1:   return sr ? {i_in1[7], vblank_l, i_in1[5:0]} : i_in1;  // srdarwin IN1 bit 6 = vblank (active high)
      R_IN2:   return lm ? {vblank_l, i_in2[6:0]} : i_in2;               // lastmisn IN2 bit 7 = vblank
      R_IN3:   return {i_in3[7:4], !vblank_l, i_in3[2:0]};               // gondo IN3 bit 3 = vblank, active low
      R_DSW0:  return i_dsw0;
      R_DSW1:  return i_dsw1;
      R_MCUHI: return mcu_return[15:8];
      R_MCULO: return mcu_return[7:0];
      R_COIN:  return i_coin;
      R_P1ROT0: return ~rot0[7:0];
      R_P1ROT1: return {~rot0[11:8], i_in0[3:0]};
      R_P2ROT0: return ~rot1[7:0];
      R_P2ROT1: return {~rot1[11:8], i_in1[3:0]};
      default: return 8'h00;
    endcase
  endfunction

  // pipeline of the read: slot -> +3 latch
  logic [2:0] rd_pipe_m, rd_pipe_s;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rd_pipe_m <= '0; rd_pipe_s <= '0;
    end else begin
      rd_pipe_m <= {rd_pipe_m[1:0], acc_m && m_rnw && md.r != R_ROM};
      rd_pipe_s <= {rd_pipe_s[1:0], acc_s && s_rnw && sd.r != R_ROM};
    end
  end

  // video address held for the read latency (CPU address of the slot)
  logic [10:0] v_addr_h;
  logic [12:0] wr_a_h;
  always_comb begin
    v_addr = acc ? ad.vaddr : v_addr_h;
    wr_a   = acc ? ad.ram : wr_a_h;
    wr_d   = adout;
    wr_we  = do_w && ad.w == W_RAM;
  end

  function automatic logic [7:0] ram_value(input rsel_t r);
    case (r)
      R_RAM:  return wr_q;
      R_PAL:  return v_pal_q;
      R_PALX: return v_palx_q;
      R_FIX:  return v_fix_q;
      R_BG:   return v_bg_q;
      R_SPR:  return v_spr_q;
      default: return port_value(r);
    endcase
  endfunction

  // MCU interface wires
  logic [7:0] mcu_p0, mcu_p1, mcu_p2, mcu_p3;
  logic       mcu_wr /* verilator public_flat_rd */, mcu_xacc;
  logic [7:0] mcu_wa /* verilator public_flat_rd */, mcu_wd /* verilator public_flat_rd */;
  wire        p2_write = has_mcu && mcu_wr && mcu_wa == 8'hA0;
  wire [7:0]  p2_fall = ~mcu_wd & mcu_p2_prev;
  wire [7:0]  p2_rise = mcu_wd & ~mcu_p2_prev;

  // lastmisn coin merger (INPUT_MERGER_ANY_LOW over COIN bits 6, 5, 7,
  // dec8:1886-1891, 852-855): high when any is pressed
  wire coin_any = !(i_coin[5] && i_coin[6] && i_coin[7]);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      mcu_value <= '0; mcu_return <= '0;
      p0_ext <= '0; p1_ext <= '0; p0_force <= '0; mcu_p2_prev <= 8'hFF;
      m_irq <= 1'b0; m_firq <= 1'b0; s_irq <= 1'b0; s_firq <= 1'b0;
      // gondo machine_reset: ghostb_bank_w(0) (dec8:1957-1962): bank 0,
      // SECCLR 0, NMI gate closed one quantum later, flip 0, strobe 0
      secclr <= 1'b0; nmi_en <= 1'b0; nmi_en_d <= 1'b0; nmi_dly <= '0;
      bank_data <= 8'h00; strobe <= 1'b0; bank <= '0;
      s_hold <= 1'b0;
      int0 <= 1'b0; int1 <= 1'b0; int1_tmr <= '0; coin_state <= 1'b0;
      m_rd <= '0; s_rd <= '0; v_addr_h <= '0; wr_a_h <= '0;
      unmapped <= '0;
      lm_scr2_pending <= 1'b0; go_scr2_pending <= 1'b0;
      o_snd_wr <= 1'b0; o_snd_data <= '0;
    end else begin
      o_snd_wr <= 1'b0;
      if (acc) begin
        v_addr_h <= ad.vaddr;
        wr_a_h <= ad.ram;
        if (acc_m) m_rs <= md.r;
        if (acc_s) s_rs <= sd.r;
        if (!ad.mapped && unmapped != 16'hFFFF) unmapped <= unmapped + 16'd1;
      end
      // read data, 3 clocks after the slot (RAM q + lane register settled)
      if (rd_pipe_m[2]) m_rd <= ram_value(m_rs);
      if (rd_pipe_s[2]) s_rd <= ram_value(s_rs);

      // ---- register writes
      if (do_w) begin
        case (ad.w)
          W_SUBIRQ_OFF:  s_irq <= 1'b0;
          W_MAINIRQ_OFF: m_irq <= 1'b0;
          W_FIRQ_OFF:    begin m_firq <= 1'b0; s_firq <= 1'b0; end
          W_MAINIRQ_ON:  m_irq <= 1'b1;
          W_SUBIRQ_ON:   s_irq <= 1'b1;
          W_SOUND:       begin o_snd_wr <= 1'b1; o_snd_data <= adout; end
          W_LMCTRL: begin
            bank <= adout[3:0];
            lm_scr2_pending <= 1'b1;
            lm_scr2_val <= {7'd0, adout[6]};
            s_hold <= !adout[7];     // bit 7 clear: hold the sub CPU in reset
          end
          W_MCULO: mcu_value[7:0] <= adout;
          W_MCUHI: begin
            mcu_value[15:8] <= adout;
            // SECIRQ (dec8:149-180): lastmisn/srdarwin when P2.1 is high,
            // gondo always (edge, cleared after 4 ticks of 1.5 MHz)
            if (go) begin int1 <= 1'b1; int1_tmr <= 9'd256; end
            else if (mcu_p2_prev[1]) int1 <= 1'b1;
          end
          W_GOBANK: begin
            bank <= adout[7:4];
            secclr <= adout[0];
            if (!adout[0]) m_irq <= 1'b0;
            if (bank_data[1] ^ adout[1]) begin nmi_en_d <= adout[1]; nmi_dly <= 6'd32; end
            bank_data <= adout;
          end
          W_SRCTRL0: bank <= {1'b0, adout[7:5]};
          default: ;
        endcase
      end
      if (lm_scr2_pending && !(do_w && ad.w == W_LMCTRL)) lm_scr2_pending <= 1'b0;
      if (go_scr2_pending && !(do_w && ad.w == W_GOSCR)) go_scr2_pending <= 1'b0;
      // gondo scroll register 0x3828 (dec8_v.cpp:132-147)
      if (do_w && ad.w == W_GOSCR && (acc_s ? s_a : m_a) == 16'h3828) begin
        go_scr2_pending <= 1'b1;
        go_scr2_val <= {7'd0, adout[1]};
        strobe <= adout[2];
      end
      // NMI enable timer: one 6309 cycle (32 clocks), MAME's
      // m_nmi_timer->adjust(minimum_quantum_time()) (dec8:204-206, R8)
      if (run && nmi_dly != 0) begin
        nmi_dly <= nmi_dly - 6'd1;
        if (nmi_dly == 6'd1) nmi_en <= nmi_en_d;
      end
      // gondo MCU INT1 auto clear (dec8:177-180, 4 ticks of 12 MHz / 8)
      if (run && int1_tmr != 0) begin
        int1_tmr <= int1_tmr - 9'd1;
        if (int1_tmr == 9'd1) int1 <= 1'b0;
      end

      // ---- MCU port writes: P0 and P1 outputs write the board latches
      // (i8751_port0_w / port1_w, dec8:695-707; srdarwin hooks P0 only)
      if (has_mcu && mcu_wr && mcu_wa == 8'h80) p0_ext <= mcu_wd;
      if (has_mcu && mcu_wr && mcu_wa == 8'h90 && !sr) p1_ext <= mcu_wd;
      // ---- MCU port 2 glue (dec8:709-790), on every write to P2
      if (p2_write) begin
        mcu_p2_prev <= mcu_wd;
        if (sr) begin
          if (p2_fall[4]) p0_ext <= mcu_value[15:8];
          if (p2_fall[5]) p0_ext <= mcu_value[7:0];
          if (p2_fall[6]) mcu_return[15:8] <= p0_ext;
          if (p2_fall[7]) mcu_return[7:0] <= p0_ext;
          if (!mcu_wd[1]) int1 <= 1'b0;
        end else begin
          if (p2_fall[4]) begin
            p0_ext <= mcu_value[15:8];
            if (lm) p0_force <= mcu_value[15:8];
          end
          if (p2_fall[5]) p1_ext <= mcu_value[7:0];
          if (p2_fall[6]) mcu_return[15:8] <= p0_ext;
          if (p2_fall[7]) mcu_return[7:0] <= p1_ext;
          if (lm) begin
            if (p2_rise[2]) begin m_firq <= 1'b1; s_firq <= 1'b1; end
            if (!mcu_wd[0]) int0 <= 1'b0;
            if (!mcu_wd[1]) int1 <= 1'b0;
          end else begin
            if (p2_rise[2] && secclr) m_irq <= 1'b1;
          end
        end
      end
      // lastmisn coin: rising edge of the merger output asserts INT0 (dec8:1886-1891)
      if (lm) begin
        coin_state <= coin_any;
        if (coin_any && !coin_state) int0 <= 1'b1;
      end
    end
  end

  // write to the video side: RAM bytes, buffer copies, scroll and flip
  always_comb begin
    v_pal_we = 1'b0; v_palx_we = 1'b0; v_fix_we = 1'b0; v_bg_we = 1'b0; v_spr_we = 1'b0;
    v_spr_copy = 1'b0; v_scr_we = 1'b0; v_scr_sel = 2'd0; v_flip_we = 1'b0; v_din = adout;
    if (do_w) begin
      case (ad.w)
        W_PAL:  v_pal_we = 1'b1;
        W_PALX: v_palx_we = 1'b1;
        W_FIX:  v_fix_we = 1'b1;
        W_BG:   v_bg_we = 1'b1;
        W_SPR:  v_spr_we = 1'b1;
        W_SPRCOPY: v_spr_copy = 1'b1;
        W_FLIP: begin v_flip_we = 1'b1; v_din = {7'd0, |adout}; end     // flip_screen_set(data)
        W_SCRX: begin v_scr_we = 1'b1; v_scr_sel = 2'd1; end
        W_SCRY: begin v_scr_we = 1'b1; v_scr_sel = 2'd3; end
        W_LMCTRL: begin v_scr_we = 1'b1; v_scr_sel = 2'd0; v_din = {7'd0, adout[5]}; end
        W_SRCTRL0: begin v_scr_we = 1'b1; v_scr_sel = 2'd0; v_din = {4'd0, adout[3:0]}; end
        W_SRCTRL1: begin v_scr_we = 1'b1; v_scr_sel = 2'd1; end
        W_GOBANK: begin v_flip_we = 1'b1; v_din = {7'd0, adout[3]}; end
        W_GOSCR: begin
          case (acc_s ? s_a : m_a)
            16'h3818: begin v_scr_we = 1'b1; v_scr_sel = 2'd1; end
            16'h3820: begin v_scr_we = 1'b1; v_scr_sel = 2'd3; end
            16'h3828: begin
              v_scr_we = 1'b1; v_scr_sel = 2'd0; v_din = {7'd0, adout[0]};
              v_spr_copy = adout[2] && !strobe;                         // rising edge (dec8:93-100)
            end
            default: ;
          endcase
        end
        default: ;
      endcase
    end else if (lm_scr2_pending) begin
      v_scr_we = 1'b1; v_scr_sel = 2'd2; v_din = lm_scr2_val;
    end else if (go_scr2_pending) begin
      v_scr_we = 1'b1; v_scr_sel = 2'd2; v_din = go_scr2_val;
    end
  end

  // CPU data inputs: ROM latch or the slot read
  always_comb begin
    m_di = (md.r == R_ROM) ? m_rom_q : m_rd;
    s_di = (sd.r == R_ROM) ? s_rom_q : s_rd;
  end

  // ================================================================ interrupts
  // MAME screen vblank: true from line 248 to the end of line 7
  logic [8:0] vc;
  always_comb vblank_l = vc >= 9'd248 || vc < 9'd8;
  always_comb begin
    m_irqn  = !m_irq;
    m_firqn = !(lm && m_firq);
    s_irqn  = !s_irq;
    s_firqn = !s_firq;
    // srdarwin: NMI = vblank (dec8:2440); gondo: NMI gate = vblank AND the
    // delayed enable (input merger, dec8:2131-2135)
    m_nmin  = !((sr && vblank_l) || (go && vblank_l && nmi_en));
  end

  // ================================================================ MCU
  // P0/P1 inputs: the external latches (dec8:689-707); P2 not hooked
  // (MAME reads 0xff); P3 = COIN. INT0: lastmisn coin, gondo vblank level
  // (dec8:2132), srdarwin not connected.
  wire int0_line = lm ? int0 : go ? vblank_l : 1'b0;
  d8_mcu u_mcu (
      .clk, .rst_n(rst_n && has_mcu), .cen(mcu_cen && has_mcu),
      .i_int0n(!int0_line), .i_int1n(!int1),
      .i_p0(p0_ext), .i_p0_force(lm ? p0_force : 8'h00),
      .i_p1(sr ? 8'hFF : p1_ext), .i_p2(8'hFF), .i_p3(i_coin),
      .o_p0(mcu_p0), .o_p1(mcu_p1), .o_p2(mcu_p2), .o_p3(mcu_p3),
      .o_sfr_wr(mcu_wr), .o_sfr_wa(mcu_wa), .o_sfr_wd(mcu_wd), .o_xacc(mcu_xacc),
      .i_rom_we(i_mcu_we), .i_rom_addr(i_mcu_addr), .i_rom_din(i_mcu_din));

  logic [15:0] xacc;
  logic        xacc_l;
  always_ff @(posedge clk) begin
    if (!rst_n) begin xacc <= '0; xacc_l <= 1'b0; end
    else begin
      xacc_l <= mcu_xacc;
      if (mcu_xacc && !xacc_l && xacc != 16'hFFFF) xacc <= xacc + 16'd1;
    end
  end
  assign o_dbg_xacc = xacc;
  assign o_dbg_unmapped = unmapped;

  // ================================================================ video
  /* verilator lint_off PINCONNECTEMPTY */
  // ================================================================ sound (M3)
  d8_snd u_snd (
    .clk(clk), .rst_n(rst_n), .i_pause(i_pause), .i_machine(i_machine),
    .i_latch_wr(o_snd_wr), .i_latch_d(o_snd_data),
    .i_rom_we(i_snd_we), .i_rom_addr(i_snd_addr), .i_rom_din(i_snd_din),
    .o_fm(o_fm), .o_ssg(o_ssg), .o_opl(o_opl), .o_mix(o_audio),
    .o_dbg_unmapped(o_dbg_snd_unmapped), .o_dbg_rom_writes());

  d8_video #(.LATCH(LATCH), .KRN_FLIP(KRN_FLIP)) u_video (
      .clk, .rst_n, .ce_pix, .i_machine,
      .i_cpu_addr(v_addr), .i_cpu_din(v_din),
      .i_pal_we(v_pal_we), .i_palx_we(v_palx_we), .i_fix_we(v_fix_we), .i_bg_we(v_bg_we),
      .i_spr_we(v_spr_we), .i_spr_copy(v_spr_copy), .i_scr_we(v_scr_we), .i_scr_sel(v_scr_sel),
      .i_flip_we(v_flip_we),
      .o_pal_dout(v_pal_q), .o_palx_dout(v_palx_q), .o_fix_dout(v_fix_q), .o_bg_dout(v_bg_q),
      .o_spr_dout(v_spr_q),
      .o_rom_req, .o_rom_addr, .i_rom_gnt, .i_rom_rv, .i_rom_data,
      .o_r, .o_g, .o_b, .o_de, .o_hblank, .o_vblank, .o_hs, .o_vs, .o_vbl, .o_vcnt(vc),
      .o_busy(), .o_hold(),
      .o_dbg_overruns, .o_dbg_maxcyc, .o_dbg_err(o_dbg_verr), .o_dbg_pen(o_pen));
  /* verilator lint_on PINCONNECTEMPTY */
  assign o_ce_pix = ce_pix;

endmodule
