//============================================================================
//  Data East DEC8 (Last Mission, Gondomania, SRD: Super Real Darwin) for
//  MiSTer - framework shell (M4)
//
//  Wraps rtl/d8_board.sv (6809s, i8751, video, sound board, SDRAM,
//  download) in the Template_MiSTer `emu` interface. The MRA selects the
//  machine with the index-1 byte (bits 1:0: 0 Last Mission, 1 Gondomania,
//  2 SRD; bit 2: the SRD bootleg without MCU) and streams the ROMs on index
//  0 (tools/make_mra.py). All three games are vertical (ROT270) and are
//  rotated through the framework's screen_rotate (DDR3 frame buffer,
//  MISTER_FB=1).
//
//  Clocks (pll.v, as the 1945k III core): 96 MHz system, a -90 degree copy
//  for SDRAM_CLK, and 48 MHz for the video path. The core's pixel enable is
//  every 16 clocks (6 MHz, spec 5); each pixel is handed to the 48 MHz
//  domain with a toggle: the core side latches the pixel and flips the
//  toggle on its enable, the video side registers the toggle and makes a
//  one-clock enable from its change.
//============================================================================

module emu
(
	`include "sys/emu_ports.vh"
);

assign ADC_BUS  = 'Z;
assign USER_OUT = '1;
assign {UART_RTS, UART_TXD, UART_DTR} = 0;
assign {SD_SCK, SD_MOSI, SD_CS} = 'Z;
assign BUTTONS = 0;
assign VGA_F1 = 1'b0;
assign VGA_SCALER = 1'b0;
assign VGA_DISABLE = 1'b0;
assign HDMI_FREEZE = 1'b0;
assign HDMI_BLACKOUT = 1'b0;
assign HDMI_BOB_DEINT = 1'b0;
assign FB_FORCE_BLANK = 1'b0;
assign AUDIO_MIX = 2'b00;

// ---------------------------------------------------------------------------
// clocks
// ---------------------------------------------------------------------------
wire clk_sys, clk_sdram, clk_vid, pll_locked;
pll pll (
	.refclk(CLK_50M),
	.rst(1'b0),
	.outclk_0(clk_sys),      // 96 MHz
	.outclk_1(clk_sdram),    // 96 MHz, -90 degrees
	.outclk_2(clk_vid),      // 48 MHz, phase aligned with clk_sys
	.locked(pll_locked)
);
assign SDRAM_CLK = clk_sdram;

// ---------------------------------------------------------------------------
// hps_io
// ---------------------------------------------------------------------------
`include "build_id.v"
localparam CONF_STR = {
	"DEC8;;",
	"-;",
	"H0OMN,Aspect ratio,Original,Full Screen,[ARC1],[ARC2];",
	"H0O2,Orientation,Vertical,Horizontal;",
	"H1O7,Rotate,CCW,CW;",
	"O35,Scandoubler Fx,None,HQ2x,CRT 25%,CRT 50%,CRT 75%;",
	"H0O[13:12],Scale,Normal,V-Integer,Narrower HV-Integer,Wider HV-Integer;",
	"O6,Pause when OSD is open,On,Off;",
	"O[9:8],Volume,Normal,+6 dB,-6 dB,-12 dB;",
	"H2O[11:10],Spinner speed,Normal,Fast,Slow;",
	"-;",
	"DIP;",
	"-;",
	"R0,Reset;",
	"J1,Button 1,Button 2,Button 3,Turn Left,Turn Right,Start,Coin,Service,Pause;",
	"jn,A,B,X,L,R,Start,Select;",
	"V,v",`BUILD_DATE
};

wire [127:0] status;
wire  [1:0] buttons;
wire        forced_scandoubler;
wire        direct_video;
wire [21:0] gamma_bus;
wire        video_rotated;

wire        ioctl_download;
wire        ioctl_wr;
wire [26:0] ioctl_addr;
wire  [7:0] ioctl_dout;
wire [15:0] ioctl_index;
wire        ioctl_wait;

wire [31:0] joystick_0, joystick_1;
wire  [7:0] paddle_0, paddle_1;
wire  [8:0] spinner_0, spinner_1;
wire [10:0] ps2_key;

wire        no_rotate;
wire  [1:0] machine;

hps_io #(.CONF_STR(CONF_STR)) hps_io (
	.clk_sys(clk_sys),
	.HPS_BUS(HPS_BUS),
	.EXT_BUS(),
	.gamma_bus(gamma_bus),
	.buttons(buttons),
	.status(status),
	.status_menumask({13'd0, machine != 2'd1, no_rotate, direct_video}),
	.forced_scandoubler(forced_scandoubler),
	.direct_video(direct_video),
	.video_rotated(video_rotated),

	.ioctl_download(ioctl_download),
	.ioctl_wr(ioctl_wr),
	.ioctl_addr(ioctl_addr),
	.ioctl_dout(ioctl_dout),
	.ioctl_index(ioctl_index),
	.ioctl_wait(ioctl_wait),
	.ioctl_upload(),
	.ioctl_upload_req(1'b0),
	.ioctl_upload_index(8'd0),
	.ioctl_din(8'd0),

	.joystick_0(joystick_0),
	.joystick_1(joystick_1),
	.paddle_0(paddle_0),
	.paddle_1(paddle_1),
	.spinner_0(spinner_0),
	.spinner_1(spinner_1),
	.ps2_key(ps2_key)
);

// ---------------------------------------------------------------------------
// keyboard, MAME default keys (ps2_key: [10] toggles per event, [9] pressed,
// [8] extended, [7:0] set-2 scancode)
//   P1: arrows, LCtrl = B1, LAlt = B2, Space = B3, Z / X = turn left /
//       right (Gondomania), 1 = Start, 5 = Coin
//   P2: R/F/D/G, A = B1, S = B2, Q = B3, N / M = turn left / right,
//       2 = Start, 6 = Coin
//   9 = Service, P = pause toggle
// ---------------------------------------------------------------------------
reg k_up, k_dn, k_lt, k_rt, k_b1, k_b2, k_b3, k_tl, k_tr, k_st1, k_co1;
reg k2_up, k2_dn, k2_lt, k2_rt, k2_b1, k2_b2, k2_b3, k2_tl, k2_tr, k_st2, k_co2;
reg k_svc;
reg ps2_last = 1'b0;
reg k_pause = 1'b0;
reg [1:0] jp_q = 2'b00;
always @(posedge clk_sys) begin
	ps2_last <= ps2_key[10];
	jp_q <= {joystick_1[12], joystick_0[12]};
	if (ps2_key[10] != ps2_last) begin
		case ({ps2_key[8], ps2_key[7:0]})
			9'h175: k_up  <= ps2_key[9];
			9'h172: k_dn  <= ps2_key[9];
			9'h16B: k_lt  <= ps2_key[9];
			9'h174: k_rt  <= ps2_key[9];
			9'h014: k_b1  <= ps2_key[9];   // left ctrl
			9'h011: k_b2  <= ps2_key[9];   // left alt
			9'h029: k_b3  <= ps2_key[9];   // space
			9'h01A: k_tl  <= ps2_key[9];   // Z
			9'h022: k_tr  <= ps2_key[9];   // X
			9'h016: k_st1 <= ps2_key[9];   // 1
			9'h01E: k_st2 <= ps2_key[9];   // 2
			9'h02E: k_co1 <= ps2_key[9];   // 5
			9'h036: k_co2 <= ps2_key[9];   // 6
			9'h046: k_svc <= ps2_key[9];   // 9
			9'h02D: k2_up <= ps2_key[9];   // R
			9'h02B: k2_dn <= ps2_key[9];   // F
			9'h023: k2_lt <= ps2_key[9];   // D
			9'h034: k2_rt <= ps2_key[9];   // G
			9'h01C: k2_b1 <= ps2_key[9];   // A
			9'h01B: k2_b2 <= ps2_key[9];   // S
			9'h015: k2_b3 <= ps2_key[9];   // Q
			9'h031: k2_tl <= ps2_key[9];   // N
			9'h03A: k2_tr <= ps2_key[9];   // M
			9'h04D: if (ps2_key[9]) k_pause <= ~k_pause;   // P
			default: ;
		endcase
	end
	// J1 Pause button on either pad toggles too
	if ((joystick_0[12] & ~jp_q[0]) | (joystick_1[12] & ~jp_q[1])) k_pause <= ~k_pause;
end
// MiSTer joystick: 0 R, 1 L, 2 D, 3 U, then the J1 list: 4 B1, 5 B2, 6 B3,
// 7 Turn Left, 8 Turn Right, 9 Start, 10 Coin, 11 Service, 12 Pause
wire [11:0] joy0 = joystick_0[11:0] | {k_svc, k_co1, k_st1, k_tr, k_tl, k_b3, k_b2, k_b1, k_up, k_dn, k_lt, k_rt};
wire [11:0] joy1 = joystick_1[11:0] | {1'b0, k_co2, k_st2, k2_tr, k2_tl, k2_b3, k2_b2, k2_b1, k2_up, k2_dn, k2_lt, k2_rt};

// ---------------------------------------------------------------------------
// inputs, active low, in MAME's port layout (dec8.cpp L824-904, L1028-1116,
// L1552-1622; the vblank bits are merged inside d8_sys)
//   Last Mission  IN0/IN1 = P1/P2: 0 up, 1 down, 2 left, 3 right, 4 shoot,
//                 5 bomb, 6 select; IN2: 2 start 1, 3 start 2;
//                 COIN: 5 coin 2, 6 coin 1, 7 service
//   Gondomania    IN0/IN1 = P1/P2 joystick in bits 0-3 (up, down, left,
//                 right; bits 4-7 read 0 as in MAME, the rotary is read
//                 elsewhere); IN2: 0 P1 B1, 1 P1 B2, 2 P2 B1, 3 P2 B2;
//                 IN3: 0 start 1, 1 start 2; COIN: 4 service, 5 coin 1,
//                 6 coin 2; rotary positions from d8_rotary
//   SRD           IN0: 0 right, 1 left, 2 up, 3 down, 4 B1, 5 B2,
//                 6 start 1, 7 start 2; IN1 = P2 bits 0-5;
//                 COIN: 5 coin 2, 6 coin 1, 7 service
// ---------------------------------------------------------------------------
wire [3:0] d1 = {joy0[0], joy0[1], joy0[2], joy0[3]};   // R, L, D, U (bits 3..0 = right..up)
wire [3:0] d2 = {joy1[0], joy1[1], joy1[2], joy1[3]};
reg  [7:0] in0, in1, in2, in3, coin;
always @(*) begin
	in2 = 8'hFF; in3 = 8'hFF;
	case (machine)
		2'd1: begin   // Gondomania
			in0  = {4'h0, ~d1};
			in1  = {4'h0, ~d2};
			in2  = {4'hF, ~joy1[5], ~joy1[4], ~joy0[5], ~joy0[4]};
			in3  = {6'h3F, ~joy1[9], ~joy0[9]};
			coin = {1'b1, ~joy1[10], ~joy0[10], ~joy0[11], 4'hF};
		end
		2'd2: begin   // SRD: right, left, up, down from bit 0
			in0  = ~{joy1[9], joy0[9], joy0[5], joy0[4], joy0[2], joy0[3], joy0[1], joy0[0]};
			in1  = ~{2'b00, joy1[5], joy1[4], joy1[2], joy1[3], joy1[1], joy1[0]};
			coin = {~joy0[11], ~joy0[10], ~joy1[10], 5'h1F};
		end
		default: begin   // Last Mission
			in0  = ~{1'b0, joy0[6], joy0[5], joy0[4], d1};
			in1  = ~{1'b0, joy1[6], joy1[5], joy1[4], d2};
			in2  = {4'hF, ~joy1[9], ~joy0[9], 2'b11};
			coin = {~joy0[11], ~joy0[10], ~joy1[10], 5'h1F};
		end
	endcase
end

// Gondomania rotary: buttons (Turn Left / Turn Right), spinner and paddle
wire reset = RESET | status[0] | buttons[1] | ioctl_download;
wire [4:0] spin_div = (status[11:10] == 2'd1) ? 5'd4 : (status[11:10] == 2'd2) ? 5'd16 : 5'd8;
wire [3:0] an0, an1;
d8_rotary rot0 (.clk(clk_sys), .reset(reset), .i_left(joy0[7]), .i_right(joy0[8]),
                .i_spinner(spinner_0), .i_paddle(paddle_0), .i_spin_div(spin_div), .o_pos(an0));
d8_rotary rot1 (.clk(clk_sys), .reset(reset), .i_left(joy1[7]), .i_right(joy1[8]),
                .i_spinner(spinner_1), .i_paddle(paddle_1), .i_spin_div(spin_div), .o_pos(an1));

// ---------------------------------------------------------------------------
// board
// ---------------------------------------------------------------------------
// Pause: the menu is open (option O6, default on) or P / the Pause button
// was pressed. d8_sys holds the CPUs, MCU and sound; video keeps scanning.
wire pause = (OSD_STATUS & ~status[6]) | k_pause;

wire [7:0] r, g, b;
wire       hbl, vbl, hs, vs, de, ce_pix;
wire signed [15:0] audio;

d8_board board (
	.clk(clk_sys), .i_sdram_rst_n(pll_locked), .i_reset(RESET | status[0] | buttons[1]),
	.i_ioctl_download(ioctl_download), .i_ioctl_wr(ioctl_wr), .i_ioctl_addr(ioctl_addr),
	.i_ioctl_dout(ioctl_dout), .i_ioctl_index(ioctl_index), .o_ioctl_wait(ioctl_wait),
	.i_in0(in0), .i_in1(in1), .i_in2(in2), .i_in3(in3), .i_coin(coin),
	.i_an0(an0), .i_an1(an1), .i_pause(pause), .i_volume(status[9:8]),
	.o_machine(machine), .o_srdb(),
	.o_r(r), .o_g(g), .o_b(b), .o_hblank(hbl), .o_vblank(vbl), .o_hs(hs), .o_vs(vs),
	.o_de(de), .o_ce_pix(ce_pix), .o_audio(audio), .o_pen(), .o_vbl(),
	.o_dbg_overruns(), .o_dbg_maxcyc(), .o_dbg_verr(), .o_dbg_prom_late(), .o_dbg_unmapped(),
	.o_dbg_xacc(), .o_dbg_snd_unmapped(), .o_dbg_ref_forced(), .o_dbg_cpu_maxlat(), .o_dbg_sub_maxlat(),
	.SDRAM_A(SDRAM_A), .SDRAM_BA(SDRAM_BA), .SDRAM_DQ(SDRAM_DQ),
	.SDRAM_DQML(SDRAM_DQML), .SDRAM_DQMH(SDRAM_DQMH), .SDRAM_nCS(SDRAM_nCS),
	.SDRAM_nRAS(SDRAM_nRAS), .SDRAM_nCAS(SDRAM_nCAS), .SDRAM_nWE(SDRAM_nWE),
	.SDRAM_CKE(SDRAM_CKE)
);

// ---------------------------------------------------------------------------
// video: 256 x 240 (MAME visarea 0-255 x 8-247), ROT270 for all three games:
// the picture is turned 90 degrees counter-clockwise (MAME). OSD Rotate CW
// turns it the other way, for monitors mounted for ROT90 games. Rotation is
// HDMI only (the frame buffer); on a CRT the picture is not rotated, and
// Gondomania and SRD have a Flip Screen DIP switch for a monitor mounted
// the other way (Last Mission has none). There is no 216-line crop: the
// picture has 240 lines.
// ---------------------------------------------------------------------------
assign no_rotate = status[2] | direct_video;
wire rotate_ccw = ~status[7];
wire flip       = 1'b0;

wire [1:0] ar = status[23:22];
wire [1:0] scale = status[13:12];

// core side: latch each pixel and flip the toggle
reg        px_tog = 1'b0;
reg  [7:0] r_h, g_h, b_h;
reg        hbl_h, vbl_h, hs_h, vs_h;
always @(posedge clk_sys) begin
	if (ce_pix) begin
		px_tog <= ~px_tog;
		{r_h, g_h, b_h} <= {r, g, b};
		{hbl_h, vbl_h, hs_h, vs_h} <= {hbl, vbl, hs, vs};
	end
end

// video side: one enable per toggle change, pixel taken one clock later
reg        tog1 = 1'b0, tog2 = 1'b0;
reg        ce_vid;
reg  [7:0] r_v, g_v, b_v;
reg        hbl_v, vbl_v, hs_v, vs_v;
always @(posedge clk_vid) begin
	tog1   <= px_tog;
	tog2   <= tog1;
	ce_vid <= (tog1 != tog2);
	if (tog1 != tog2) begin
		{r_v, g_v, b_v} <= {r_h, g_h, b_h};
		{hbl_v, vbl_v, hs_v, vs_v} <= {hbl_h, vbl_h, hs_h, vs_h};
	end
end

screen_rotate screen_rotate (.*);

wire vga_de_mix;
arcade_video #(.WIDTH(256), .DW(24)) arcade_video (
	.*,
	.clk_video(clk_vid),
	.ce_pix(ce_vid),
	.RGB_in({r_v, g_v, b_v}),
	.HBlank(hbl_v),
	.VBlank(vbl_v),
	.HSync(hs_v),
	.VSync(vs_v),
	.fx(status[5:3]),
	.VGA_DE(vga_de_mix)
);

video_freak video_freak (
	.CLK_VIDEO(CLK_VIDEO),
	.CE_PIXEL(CE_PIXEL),
	.VGA_VS(VGA_VS),
	.HDMI_WIDTH(HDMI_WIDTH),
	.HDMI_HEIGHT(HDMI_HEIGHT),
	.VGA_DE(VGA_DE),
	.VIDEO_ARX(VIDEO_ARX),
	.VIDEO_ARY(VIDEO_ARY),
	.VGA_DE_IN(vga_de_mix),
	.ARX((!ar) ? ((no_rotate) ? 12'd4 : 12'd3) : {10'd0, ar - 2'd1}),
	.ARY((!ar) ? ((no_rotate) ? 12'd3 : 12'd4) : 12'd0),
	.CROP_SIZE(12'd0),
	.CROP_OFF(5'd0),
	.SCALE({1'b0, scale})
);

// ---------------------------------------------------------------------------
// audio / LEDs (mono board)
// ---------------------------------------------------------------------------
assign AUDIO_L = audio;
assign AUDIO_R = audio;
assign AUDIO_S = 1'b1;

assign LED_USER  = ioctl_download;
assign LED_POWER = 2'b00;
assign LED_DISK  = 2'b00;

endmodule
