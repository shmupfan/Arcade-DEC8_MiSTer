// M4 board harness for d8_board + SDRAM model (sim/m4/tb_board.sv).
//
// Everything arrives as on the MiSTer: the machine byte (ioctl index 1), the
// ROM stream (index 0: +stream=FILE, the bytes the set's MRA assembles,
// written by tools/make_mra.py as sim/build/regions/<set>/stream.bin) and the
// DIP switches (index 254) go through d8_board's ioctl port, honouring
// ioctl_wait, into d8_sdram, the SDRAM model and the MCU / sound program
// block RAMs. Then the system runs from power-on: both 6809 program ROMs and
// the graphics come from the SDRAM controller and the cycle-checked SDRAM
// model, not from C++ models.
//
// Outputs are the M2 harness's (m2/tb_sys.cpp), same names, formats and
// frame numbering, so m4/compare_m2.py checks a board run against the M2
// run of the same game byte for byte, and m2/compare.py against MAME:
//   NNNNNN.rgbp, .wlog for every frame in +cap=FILE; at vblank N .pal .palx
//   .fix .bg .sprl .sprb .ram .mcu .snd .regs; +io=FILE, +ints=FILE,
//   +snd=FILE. Vblank N = the N-th o_vbl after the core is released
//   (d8_board's core_run), as M2's N-th o_vbl after reset.
// Video while the core is held in reset (download, SDRAM init): vsync edges
// and lit pixels are counted and printed (PRE-RUN line); the picture must be
// black with sync running.
// Audio: every clock, o_audio must equal d8_sys's mix three clocks earlier
// times the machine's gain (38, 40, 27 / 16) at the default volume,
// saturated (d8_board); mismatches, saturated clocks and the peak are
// printed with the counters.
//
// Plusargs: +stream=FILE +set=NAME +frames=N +cap=FILE +out=DIR +io=FILE
//   +ints=FILE +snd=FILE +inputs=FILE +inlag=N (default 1) +pause=F:N
//   +first=STREAM:SET:FRAMES run another game first (download it, run it
//   for FRAMES vblanks), then load the game under test with a new download,
//   as the MiSTer does when a second MRA for the same core is loaded without
//   reconfiguring the FPGA. Frame numbering restarts with the second game.

#include "Vtb_board.h"
#include "Vtb_board___024root.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <unistd.h>
#include <vector>

static std::unique_ptr<Vtb_board> top;
static uint64_t cycles = 0;
static bool run_on = false;            // d8_board core_run, sampled each clock
static int vphase = 0;                 // 0 = core not yet running
static long vs_edges[2], lit_px[2], de_px[2];
static bool vs_prev = false;
static long aud_bad = 0, aud_sat = 0;
static int aud_peak = 0;
static int mix_d[3] = {0, 0, 0};
static bool aud_have = false;
static int gain_of(int mach) { return mach == 1 ? 40 : mach == 2 ? 27 : 38; }
static int cur_gain = 38;

static void tick() {
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
    cycles++;
    auto *r = top->rootp;
    run_on = r->tb_board__DOT__u_board__DOT__core_run;
    bool vs = top->o_vs;
    if (vs && !vs_prev) vs_edges[vphase]++;
    vs_prev = vs;
    if (top->o_de && top->o_ce_pix) {
        de_px[vphase]++;
        if (top->o_r | top->o_g | top->o_b) lit_px[vphase]++;
    }
    if (run_on && vphase == 0) {
        printf("PRE-RUN vs_edges %ld de_px %ld lit_px %ld (clock %llu)\n", vs_edges[0], de_px[0], lit_px[0],
               (unsigned long long)cycles);
        fflush(stdout);
        vs_edges[0] = de_px[0] = lit_px[0] = 0;
        vphase = 1;
    }
    // audio: o_audio(t) = sat(mix(t-3) * gain / 16) at volume 0
    int a = (int16_t)top->o_audio;
    if (aud_have) {
        int sum = (mix_d[2] * cur_gain) >> 4;      // arithmetic shift, as the RTL
        int e = sum > 32767 ? 32767 : sum < -32768 ? -32768 : sum;
        if (e != sum) aud_sat++;
        if (a != e) aud_bad++;
    }
    if ((a < 0 ? -a : a) > aud_peak) aud_peak = a < 0 ? -a : a;
    mix_d[2] = mix_d[1];
    mix_d[1] = mix_d[0];
    mix_d[0] = (int16_t)r->tb_board__DOT__u_board__DOT__mix;
    aud_have = true;
}

static std::string plus(const char *name, const char *def) {
    const char *v = Verilated::commandArgsPlusMatch(name);
    if (!v || !*v) return def;
    const char *eq = strchr(v, '=');
    return eq ? std::string(eq + 1) : std::string(def);
}

static void dump(const std::string &path, const void *p, size_t n) {
    std::ofstream o(path, std::ios::binary);
    o.write((const char *)p, n);
}

// 16-bit snapram words to MAME's byte order: word i = {byte 2i, byte 2i+1}
template <typename A> static void dumpw(const std::string &path, const A &mem, int nwords, int nbytes) {
    std::vector<uint8_t> b(2 * nwords);
    for (int i = 0; i < nwords; i++) { uint16_t w = mem[i]; b[2 * i] = w >> 8; b[2 * i + 1] = w & 0xFF; }
    b.resize(nbytes);
    dump(path, b.data(), b.size());
}

// ----------------------------------------------------------------- sets
enum { LM = 0, GO = 1, SR = 2 };
struct SetInfo { int machine; bool srdb; uint8_t in0, in1, in2, in3, coin, dsw0, dsw1; };
// port values at power-on, read from MAME (sim/m2/ports_probe.lua,
// build/m2_ports_probe.txt), vblank bits excluded (the core sets them)
static bool set_info(const std::string &s, SetInfo &si) {
    if (s == "lastmisn" || s == "lastmisnu6" || s == "lastmisnu5")
        si = {LM, false, 0xFF, 0xFF, 0x7F, 0xFF, 0xFF, 0xCF, 0x7F};
    else if (s == "lastmisnj") si = {LM, false, 0xFF, 0xFF, 0x7F, 0xFF, 0xFF, 0xCF, 0xFF};
    else if (s == "gondo" || s == "gondou" || s == "makyosen")
        si = {GO, false, 0x0F, 0x0F, 0xFF, 0xFF, 0xFF, 0xFF, 0xEF};
    else if (s == "srdarwin" || s == "srdarwinj") si = {SR, false, 0xFF, 0xBF, 0xFF, 0xFF, 0xFF, 0x7F, 0xFF};
    else if (s == "srdarwinb") si = {SR, true, 0xFF, 0xBF, 0xFF, 0xFF, 0xFF, 0x7F, 0xFF};
    else return false;
    return true;
}

// inputs.csv (port, field) -> (port index 0 IN0 1 IN1 2 IN2 3 IN3 4 COIN 5 DSW0 6 DSW1, bit)
static bool field_bit(int mach, const std::string &port, const std::string &field, int &p, int &bit) {
    static const std::map<std::string, int> P = {{"IN0", 0}, {"IN1", 1}, {"IN2", 2}, {"IN3", 3},
                                                  {"COIN", 4}, {"DSW0", 5}, {"DSW1", 6}};
    auto it = P.find(port);
    if (it == P.end()) return false;
    p = it->second;
    std::map<std::string, int> b;
    if (mach == LM) {
        b = {{"P1 Up", 0}, {"P1 Down", 1}, {"P1 Left", 2}, {"P1 Right", 3}, {"P1 Button 1", 4}, {"P1 Button 2", 5},
             {"P1 Button 3", 6}, {"P2 Up", 0}, {"P2 Down", 1}, {"P2 Left", 2}, {"P2 Right", 3}, {"P2 Button 1", 4},
             {"P2 Button 2", 5}, {"P2 Button 3", 6}, {"1 Player Start", 2}, {"2 Players Start", 3},
             {"Coin 1", 6}, {"Coin 2", 5}, {"Service 1", 7}};
    } else if (mach == GO) {
        b = {{"P1 Up", 0}, {"P1 Down", 1}, {"P1 Left", 2}, {"P1 Right", 3}, {"P2 Up", 0}, {"P2 Down", 1},
             {"P2 Left", 2}, {"P2 Right", 3}, {"P1 Button 1", 0}, {"P1 Button 2", 1}, {"P2 Button 1", 2},
             {"P2 Button 2", 3}, {"1 Player Start", 0}, {"2 Players Start", 1}, {"Service 1", 4},
             {"Coin 1", 5}, {"Coin 2", 6}, {"Flip Screen", 6}};
    } else {
        b = {{"P1 Right", 0}, {"P1 Left", 1}, {"P1 Up", 2}, {"P1 Down", 3}, {"P1 Button 1", 4}, {"P1 Button 2", 5},
             {"1 Player Start", 6}, {"2 Players Start", 7}, {"P2 Right", 0}, {"P2 Left", 1}, {"P2 Up", 2},
             {"P2 Down", 3}, {"P2 Button 1", 4}, {"P2 Button 2", 5}, {"Coin 2", 5}, {"Coin 1", 6},
             {"Service 1", 7}, {"Flip Screen", 6}};
    }
    auto fb = b.find(field);
    if (fb == b.end()) return false;
    bit = fb->second;
    return true;
}

// the non-heavy write classes of d8_oracle.lua MAPS (what writes.csv logs)
static bool logged(int mach, bool sub, unsigned a) {
    if (mach == LM) {
        if (a >= 0x1800 && a <= 0x180f) {
            switch (a) {
                case 0x1800: case 0x1801: case 0x1802: case 0x1803: case 0x1804: case 0x1805:
                case 0x1807: case 0x180c: case 0x180e: case 0x180f: return true;
                case 0x1809: case 0x180b: case 0x180d: return !sub;
                default: return false;
            }
        }
        return a >= 0x4000;
    }
    if (mach == GO)
        return a == 0x3810 || (a >= 0x3818 && a <= 0x382f) || a == 0x3830 || a == 0x383a || a == 0x383b ||
               a >= 0x4000;
    return (a >= 0x1800 && a <= 0x1801) || (a >= 0x1803 && a <= 0x1806) || a == 0x2000 || a == 0x2001 ||
           a >= 0x4000;
}
// writes the frame's .wlog keeps (video side, for the image check)
static bool vid_write(int mach, unsigned a) {
    if (mach == LM) return (a >= 0x1000 && a < 0x1800) || (a >= 0x2000 && a < 0x3000) || (a >= 0x3800 && a < 0x4000) ||
                           a == 0x1805 || a == 0x1807 || a == 0x1809 || a == 0x180b || a == 0x180d;
    if (mach == GO) return (a >= 0x1800 && a < 0x3800) || (a >= 0x3818 && a <= 0x3830);
    return (a >= 0x0600 && a < 0x1000) || (a >= 0x1400 && a < 0x1800) || a == 0x1804 || a == 0x1805 ||
           a == 0x1806 || a == 0x2001 || (a >= 0x2800 && a <= 0x288f) || (a >= 0x3000 && a <= 0x308f);
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    top = std::make_unique<Vtb_board>();
    std::string setn = plus("set", ""), stf = plus("stream", ""), out = plus("out", ".");
    std::string capf = plus("cap", "");
    SetInfo si;
    if (!set_info(setn, si)) { fprintf(stderr, "unknown set %s\n", setn.c_str()); return 2; }
    long nframes = atol(plus("frames", "600").c_str());
    long pause_f = -1, pause_n = 0;
    {
        std::string ps = plus("pause", "");
        if (!ps.empty()) sscanf(ps.c_str(), "%ld:%ld", &pause_f, &pause_n);
    }
    std::vector<uint8_t> stream;
    {
        std::ifstream f(stf, std::ios::binary);
        if (!f) { fprintf(stderr, "cannot open stream %s\n", stf.c_str()); return 2; }
        stream.assign(std::istreambuf_iterator<char>(f), {});
    }
    std::set<long> cap;
    if (!capf.empty()) {
        std::ifstream f(capf);
        long n;
        while (f >> n) cap.insert(n);
    }
    uint8_t ports[7] = {si.in0, si.in1, si.in2, si.in3, si.coin, si.dsw0, si.dsw1};
    std::multimap<long, std::tuple<int, int, int>> events;
    const int inlag = atoi(plus("inlag", "1").c_str());
    {
        std::string inf = plus("inputs", "");
        if (!inf.empty()) {
            std::ifstream f(inf);
            std::string ln;
            std::getline(f, ln);
            while (std::getline(f, ln)) {
                std::stringstream ss(ln);
                std::string fr, port, field, val;
                std::getline(ss, fr, ','); std::getline(ss, port, ',');
                std::getline(ss, field, ','); std::getline(ss, val, ',');
                int p, bit;
                if (!field_bit(si.machine, port, field, p, bit)) {
                    fprintf(stderr, "unknown input %s %s\n", port.c_str(), field.c_str());
                    return 2;
                }
                if (val.compare(0, 11, "user_value=") == 0) {   // DIP set at start (FIELDS)
                    int v = atoi(val.c_str() + 11);
                    if (v) ports[p] |= 1u << bit; else ports[p] &= ~(1u << bit);
                    continue;
                }
                events.insert({atol(fr.c_str()) + inlag, {p, bit, atoi(val.c_str())}});
            }
        }
    }
    // +mcutrace=F0:F1:FILE: every MCU SFR write from vblank F0 to F1
    long mt0 = -1, mt1 = -1;
    char mt_file[512] = {0};
    {
        std::string ms = plus("mcutrace", "");
        if (!ms.empty()) sscanf(ms.c_str(), "%ld:%ld:%511s", &mt0, &mt1, mt_file);
    }
    FILE *fmcu = mt_file[0] ? fopen(mt_file, "w") : nullptr;
    // +pctrace=F0:F1:FILE: every opcode fetch (main and sub) from vblank F0 to F1
    long tr0 = -1, tr1 = -1;
    char tr_file[512] = {0};
    {
        std::string ts = plus("pctrace", "");
        if (!ts.empty()) sscanf(ts.c_str(), "%ld:%ld:%511s", &tr0, &tr1, tr_file);
    }
    FILE *ftr = tr_file[0] ? fopen(tr_file, "w") : nullptr;
    // +bustrace=F0:F1:FILE: every bus cycle at falling E (addr, R/W, data)
    long bt0 = -1, bt1 = -1;
    char bt_file[512] = {0};
    {
        std::string bs = plus("bustrace", "");
        if (!bs.empty()) sscanf(bs.c_str(), "%ld:%ld:%511s", &bt0, &bt1, bt_file);
    }
    FILE *fbus = bt_file[0] ? fopen(bt_file, "w") : nullptr;
    FILE *fsnd = nullptr, *faud = nullptr;
    {
        std::string sf = plus("snd", ""), af = plus("aud", "");
        if (!sf.empty()) { fsnd = fopen(sf.c_str(), "w"); fprintf(fsnd, "t,frame,kind,addr,data\n"); }
        if (!af.empty()) faud = fopen(af.c_str(), "wb");
    }
    // +sndtrace=F0:F1:FILE: every 6502 opcode fetch from vblank F0 to F1,
    // "t,pc,op" (t in seconds from reset); instruction lengths in bus
    // cycles are the differences x 1.5 MHz (m3_findings, cycle audit)
    long st0 = -1, st1 = -1;
    char st_file[512] = {0};
    {
        std::string ss = plus("sndtrace", "");
        if (!ss.empty()) sscanf(ss.c_str(), "%ld:%ld:%511s", &st0, &st1, st_file);
    }
    FILE *fstr = st_file[0] ? fopen(st_file, "w") : nullptr;
    FILE *fio = nullptr, *fint = nullptr;
    {
        std::string iof = plus("io", ""), inf = plus("ints", "");
        if (!iof.empty()) fio = fopen(iof.c_str(), "w");
        if (!inf.empty()) fint = fopen(inf.c_str(), "w");
    }
    auto apply_ports = [&]() {
        top->i_in0 = ports[0]; top->i_in1 = ports[1]; top->i_in2 = ports[2]; top->i_in3 = ports[3];
        top->i_coin = ports[4];
    };
    top->i_pause = 0;
    top->i_volume = 0;
    top->i_an0 = 0; top->i_an1 = 0;
    apply_ports();
    top->i_reset = 1; top->i_sdram_rst_n = 0;
    top->i_ioctl_download = 0; top->i_ioctl_wr = 0; top->i_ioctl_index = 0;
    for (int i = 0; i < 16; i++) tick();
    top->i_sdram_rst_n = 1;
    for (int i = 0; i < 256; i++) tick();

    auto send = [&](int index, uint32_t addr, uint8_t data) {
        while (top->o_ioctl_wait) tick();
        top->i_ioctl_index = index; top->i_ioctl_addr = addr; top->i_ioctl_dout = data;
        top->i_ioctl_wr = 1;
        tick();
        top->i_ioctl_wr = 0;
        tick();
    };
    // as Main_MiSTer sends an MRA: index 1 (machine byte), the ROM stream
    // (index 0), then the DIP switches (index 254); then the core is
    // released on the raster's power-on phase (core_run)
    auto download = [&](const std::vector<uint8_t> &im, const SetInfo &s2, uint8_t d0, uint8_t d1) {
        uint64_t t = cycles;
        top->i_reset = 1;
        vphase = 0;
        top->i_ioctl_download = 1;
        send(1, 0, (uint8_t)(s2.machine | (s2.srdb ? 4 : 0)));
        top->i_ioctl_download = 0;
        for (int i = 0; i < 64; i++) tick();
        top->i_ioctl_download = 1;
        for (size_t k = 0; k < im.size(); k++) send(0, (uint32_t)k, im[k]);
        top->i_ioctl_download = 0;
        for (int i = 0; i < 64; i++) tick();
        top->i_ioctl_download = 1;
        send(254, 0, d0);
        send(254, 1, d1);
        top->i_ioctl_download = 0;
        for (int i = 0; i < 64; i++) tick();
        cur_gain = gain_of(s2.machine);
        printf("download: %s machine %d srdb %d, %zu bytes in %llu clocks\n", setn.c_str(), s2.machine, s2.srdb,
               im.size(), (unsigned long long)(cycles - t));
        fflush(stdout);
        top->i_reset = 0;
        while (!run_on) tick();
    };
    {
        std::string fs = plus("first", "");
        if (!fs.empty()) {
            char path[512], fset[64]; long ff = 0;
            if (sscanf(fs.c_str(), "%511[^:]:%63[^:]:%ld", path, fset, &ff) != 3) { fprintf(stderr, "bad +first\n"); return 2; }
            SetInfo fi;
            if (!set_info(fset, fi)) { fprintf(stderr, "unknown +first set %s\n", fset); return 2; }
            std::ifstream f(path, std::ios::binary);
            std::vector<uint8_t> im((std::istreambuf_iterator<char>(f)), {});
            download(im, fi, fi.dsw0, fi.dsw1);
            long v = 0;
            while (v < ff) { tick(); if (top->o_vbl) v++; }
            printf("first game %s ran %ld vblanks\n", fset, v);
        }
    }
    download(stream, si, ports[5], ports[6]);
    const uint64_t t0 = cycles;

    auto *r = top->rootp;
    const int mach = si.machine;
    long frame = 0;
    std::vector<uint8_t> px;
    px.reserve(256 * 240 * 5);
    std::string wlog;
    int ints[5] = {0, 0, 0, 0, 0};
    while (frame < nframes) {
        // bus events going into this clock edge
        bool am = r->tb_board__DOT__u_board__DOT__u_sys__DOT__at_m, as = r->tb_board__DOT__u_board__DOT__u_sys__DOT__at_s;
        int line = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__vcnt, hp = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__hcnt;
        if (fbus && frame >= bt0 && frame < bt1 && r->tb_board__DOT__u_board__DOT__u_sys__DOT__cen_E) {
            fprintf(fbus, "%ld %d %d main %04x %c %02x\n", frame, line, hp, r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_a,
                    r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_rnw ? 'R' : 'W', r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_rnw ? r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_di : r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_do);
            if (mach == LM)
                fprintf(fbus, "%ld %d %d sub %04x %c %02x\n", frame, line, hp, r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_a,
                        r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_rnw ? 'R' : 'W', r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_rnw ? r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_di : r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_do);
        }
        if (ftr && frame >= tr0 && frame < tr1) {
            if (am && r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_op && r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_rnw)
                fprintf(ftr, "%ld %d %d main %04x\n", frame, line, hp, r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_a);
            if (as && r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_op && r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_rnw)
                fprintf(ftr, "%ld %d %d sub %04x\n", frame, line, hp, r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_a);
        }
        for (int c = 0; c < 2; c++) {
            bool a_on = c ? as : am;
            if (!a_on) continue;
            unsigned a = c ? r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_a : r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_a;
            bool rnw = c ? r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_rnw : r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_rnw;
            unsigned d = c ? r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_do : r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_do;
            if (!rnw) {
                if (fio && logged(mach, c, a))
                    fprintf(fio, "%ld %d %d %s %04x %x\n", frame, line, hp, c ? "sub" : "main", a, d);
                if (cap.count(frame) && vid_write(mach, a)) {
                    char b[64];
                    snprintf(b, sizeof b, "%d %d %s %04x %02x\n", line, hp, c ? "sub" : "main", a, d);
                    wlog += b;
                }
            } else {
                if (a == 0xfffc && !c) ints[0]++;
                if (a == 0xfff8) ints[c ? 3 : 1]++;
                if (a == 0xfff6) ints[c ? 4 : 2]++;
            }
        }
        if (fsnd || faud) {
            static bool prd = false; static unsigned pa = 0xFFFFFFFF;
            double t = (double)(cycles - t0) / 96e6;
            if (fsnd && r->tb_board__DOT__u_board__DOT__u_sys__DOT__o_snd_wr)
                fprintf(fsnd, "%.12f,%ld,L,%x,%x\n", t, frame, mach == LM ? 0x180c : mach == GO ? 0x3810 : 0x2000,
                        r->tb_board__DOT__u_board__DOT__u_sys__DOT__o_snd_data);
            if (fstr && frame >= st0 && frame < st1 && r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__cpu_cen) {
                static bool pf = false; static unsigned pfa = 0xFFFFFFFF;
                bool f = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__fetch && r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__rd;
                unsigned a = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__A;
                if (f && (!pf || a != pfa)) fprintf(fstr, "%.9f,%x,%x\n", t, a, r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__din);
                pf = f; pfa = a;
            }
            if (fsnd && r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__cpu_cen) {
                unsigned a = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__A;
                bool rdn = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__rd && !r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__wr;
                unsigned ym = mach == LM ? 0x0800 : 0x2000, opl = mach == LM ? 0x1000 : 0x4000, lat = mach == LM ? 0x3000 : 0x6000;
                if (r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__wev) {
                    unsigned d = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__dout;
                    if ((a & ~1u) == ym) fprintf(fsnd, "%.12f,%ld,Y,%x,%x\n", t, frame, a, d);
                    else if ((a & ~1u) == opl) fprintf(fsnd, "%.12f,%ld,P,%x,%x\n", t, frame, a, d);
                    else if (a >= 0x0600 && a < 0x8000 && a != lat) fprintf(fsnd, "%.12f,%ld,U,%x,%x\n", t, frame, a + 0x10000, d);
                }
                if (rdn && (!prd || a != pa)) {
                    unsigned d = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__din;
                    if ((a & ~1u) == ym || (a & ~1u) == opl || a == lat) fprintf(fsnd, "%.12f,%ld,R,%x,%x\n", t, frame, a, d);
                    else if (a >= 0x0600 && a < 0x8000) fprintf(fsnd, "%.12f,%ld,U,%x,%x\n", t, frame, a, d);
                    else if (a == 0xfffa) fprintf(fsnd, "%.12f,%ld,N,%x,%x\n", t, frame, a, d);
                    else if (a == 0xfffe) fprintf(fsnd, "%.12f,%ld,I,%x,%x\n", t, frame, a, d);
                }
                prd = rdn; pa = a;
            }
            if (faud && (cycles - t0) % 2000 == 0) {
                // board: {o_audio, 0, 0, d8_sys mix}; channel 3 = M2's channel 3
                int16_t v[4] = {(int16_t)top->o_audio, 0, 0, (int16_t)r->tb_board__DOT__u_board__DOT__mix};
                fwrite(v, 2, 4, faud);
            }
        }
        bool ce = top->o_ce_pix;
        if (fmcu && r->tb_board__DOT__u_board__DOT__u_sys__DOT__mcu_wr && frame >= mt0 && frame < mt1)
            fprintf(fmcu, "%ld %d %d sfr %02x %02x int1 %d int0 %d\n", frame, line, hp, r->tb_board__DOT__u_board__DOT__u_sys__DOT__mcu_wa,
                    r->tb_board__DOT__u_board__DOT__u_sys__DOT__mcu_wd, r->tb_board__DOT__u_board__DOT__u_sys__DOT__int1, r->tb_board__DOT__u_board__DOT__u_sys__DOT__int0);
        tick();
        if (ce && top->o_de) {
            px.push_back(top->o_r);
            px.push_back(top->o_g);
            px.push_back(top->o_b);
            px.push_back(top->o_pen & 0xFF);
            px.push_back(top->o_pen >> 8);
        }
        if (top->o_vbl) {
            if (frame > 0 && cap.count(frame)) {
                char fn[128];
                snprintf(fn, sizeof fn, "%s/%06ld.rgbp", out.c_str(), frame);
                if (px.size() != 256 * 240 * 5) fprintf(stderr, "frame %ld: %zu pixels\n", frame, px.size() / 5);
                dump(fn, px.data(), px.size());
                snprintf(fn, sizeof fn, "%s/%06ld.wlog", out.c_str(), frame);
                dump(fn, wlog.data(), wlog.size());
            }
            wlog.clear();
            px.clear();
            frame++;
            if (fint) fprintf(fint, "%ld %d %d %d %d %d\n", frame, ints[0], ints[1], ints[2], ints[3], ints[4]);
            for (int &i : ints) i = 0;
            for (auto it = events.lower_bound(frame); it != events.upper_bound(frame); ++it) {
                auto [p, bit, v] = it->second;
                if (v) ports[p] &= ~(1u << bit); else ports[p] |= 1u << bit;
            }
            apply_ports();
            top->i_pause = pause_f >= 0 && frame >= pause_f && frame < pause_f + pause_n;
            if (cap.count(frame)) {
                std::string base = out + "/" + std::to_string(1000000 + frame).substr(1);
                auto &v = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__u_pal__DOT__g_plain__DOT__u_l__DOT__mem;
                std::vector<uint8_t> pal(1024), palx(1024);
                for (int i = 0; i < 1024; i++) { pal[i] = v[i] & 0xFF; palx[i] = v[i] >> 8; }
                dump(base + ".pal", pal.data(), 1024);
                dump(base + ".palx", palx.data(), 1024);
                dumpw(base + ".fix", r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__u_fix__DOT__g_plain__DOT__u_l__DOT__mem, 1024, 2048);
                dumpw(base + ".bg", r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__u_bg__DOT__g_plain__DOT__u_l__DOT__mem, 1024, 2048);
                dumpw(base + ".sprl", r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__u_spr__DOT__g_snap__DOT__u_l__DOT__mem, 1024, 2048);
                dumpw(base + ".sprb", r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_video__DOT__u_spr__DOT__g_snap__DOT__g_one__DOT__u_s__DOT__mem, 1024, 2048);
                std::vector<uint8_t> ram(8192), mram(128);
                for (int i = 0; i < 8192; i++) ram[i] = r->tb_board__DOT__u_board__DOT__u_sys__DOT__wram[i];
                for (int i = 0; i < 128; i++) mram[i] = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_mcu__DOT__ram[i];
                dump(base + ".ram", ram.data(), ram.size());
                dump(base + ".mcu", mram.data(), mram.size());
                std::vector<uint8_t> sram(1536);
                for (int i = 0; i < 1536; i++) sram[i] = r->tb_board__DOT__u_board__DOT__u_sys__DOT__u_snd__DOT__ram[i];
                dump(base + ".snd", sram.data(), sram.size());
                FILE *fr = fopen((base + ".regs").c_str(), "w");
                fprintf(fr, "bank %d m_irq %d m_firq %d s_irq %d s_firq %d int0 %d int1 %d\n",
                        r->tb_board__DOT__u_board__DOT__u_sys__DOT__bank, r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_irq, r->tb_board__DOT__u_board__DOT__u_sys__DOT__m_firq,
                        r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_irq, r->tb_board__DOT__u_board__DOT__u_sys__DOT__s_firq, r->tb_board__DOT__u_board__DOT__u_sys__DOT__int0, r->tb_board__DOT__u_board__DOT__u_sys__DOT__int1);
                fclose(fr);
            }
            if (frame % 500 == 0) {
                printf("vblank %ld overruns %d maxcyc %d verr %d promlate %d unmapped %d xacc %d sndunm %d "
                       "cpu_maxlat %d sub_maxlat %d ref_forced %d aud_bad %ld aud_sat %ld aud_peak %d\n", frame,
                       top->o_dbg_overruns, top->o_dbg_maxcyc, top->o_dbg_verr, top->o_dbg_prom_late,
                       top->o_dbg_unmapped, top->o_dbg_xacc, top->o_dbg_snd_unmapped, top->o_dbg_cpu_maxlat,
                       top->o_dbg_sub_maxlat, top->o_dbg_ref_forced, aud_bad, aud_sat, aud_peak);
                fflush(stdout);
            }
        }
    }
    printf("DONE vblanks %ld cycles %llu overruns %d maxcyc %d verr %d promlate %d unmapped %d xacc %d sndunm %d\n", frame,
           (unsigned long long)cycles, top->o_dbg_overruns, top->o_dbg_maxcyc, top->o_dbg_verr,
           top->o_dbg_prom_late, top->o_dbg_unmapped, top->o_dbg_xacc, top->o_dbg_snd_unmapped);
    printf("SDRAM cpu_maxlat %d sub_maxlat %d ref_forced %d; audio mismatches %ld saturated %ld peak %d; "
           "running: vs_edges %ld lit_px %ld\n", top->o_dbg_cpu_maxlat, top->o_dbg_sub_maxlat, top->o_dbg_ref_forced,
           aud_bad, aud_sat, aud_peak, vs_edges[1], lit_px[1]);
    if (fio) fclose(fio);
    if (fsnd) fclose(fsnd);
    if (fstr) fclose(fstr);
    if (faud) fclose(faud);
    if (fint) fclose(fint);
    if (fmcu) fclose(fmcu);
    if (ftr) fclose(ftr);
    if (fbus) fclose(fbus);
    top->final();
    top.reset();
    fflush(stdout);
    _exit(0);
}
