// M2 full-system harness for d8_sys (Verilator, C++), after the 1945k III and
// Tecmo 16 M2 harnesses.
//
// Loads the set's sdram.bin (tools/build_regions.py SDRAM_SLOTS: maincpu
// 0x000000, mainbank 0x010000, sub 0x050000, mcu 0x080000) and gfx.bin (the
// graphics port image, tools/gfx_layout.py), loads the MCU program ROM,
// resets and runs the system from power-on.
//
// Frame numbering: vblank N = the N-th o_vbl (start of line 248), the same
// instant as MAME's N-th frame notifier (d8_oracle.lua). Displayed frame N =
// the pixels scanned out between vblank N and N+1 (MAME's frame N+1).
//
// Outputs in +out=DIR for every frame number in +cap=FILE:
//   NNNNNN.rgbp   displayed frame N: 256 x 240 x 5 (R, G, B, pen lo, pen hi)
//   NNNNNN.wlog   every CPU write to palette, fix, bg, sprite RAM, scroll,
//                 flip, control or the sprite copy during displayed frame N:
//                 "line hpos cpu addr data"
//   at vblank N, MAME's byte order (d8_oracle.lua):
//   .pal .palx (1 KB each), .fix .bg .sprl .sprb (2 KB each), .ram (8 KB,
//   d8_sys work RAM layout), .mcu (128 bytes), .regs (text)
// Whole run:
//   +io=FILE   every CPU write MAME's oracle logs in writes.csv (the
//              non-heavy classes of d8_oracle.lua MAPS) as
//              "vblank line hpos cpu addr data"
//   +ints=FILE per vblank "vblank main_nmi main_irq main_firq sub_irq
//              sub_firq": interrupt vector high-byte reads (FFFC, FFF8, FFF6),
//              MAME's frames.csv columns
//
// Plusargs: +sdram=FILE +gfx=FILE +set=NAME +frames=N +cap=FILE +out=DIR
//   +inputs=FILE: the oracle's inputs.csv; events applied at vblank
//   frame + inlag (+inlag=N, default 1, as the other cores: MAME latches
//   field values at its next input update)
//   +promlat=N program ROM clocks from request to ok (default 9, the SDRAM
//   controller's worst case in the other cores)
//   graphics ROM model as m1/tb_video.cpp: +intv=N (8) +lat=N (9)
//   +pause=F:N hold i_pause for N frames from vblank F
//   M3 (sound board, d8_snd): the sound ROM (sdram 0x068000-0x06FFFF) is
//   loaded before reset; +snd=FILE writes every sound event as the
//   oracle's sndlog.csv ("t,frame,kind,addr,data", t in seconds from reset
//   release): L main latch write, Y/P 6502 write to the YM2203 / OPL, R
//   6502 read of the latch or a chip, U other unmapped access, N/I 6502 read
//   of FFFA / FFFE (interrupt vector, low byte); +aud=FILE writes 48 kHz
//   frames of 4 int16 (FM, SSG, OPL, mix) sampled every 2000 clocks; at
//   every capture frame the 6502 RAM (0000-05FF) as .snd

#include "Vd8_sys.h"
#include "Vd8_sys___024root.h"
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

static std::unique_ptr<Vd8_sys> top;
static std::vector<uint8_t> sdram, gfx;
static int lat = 9, intv = 8, promlat = 9;
static uint64_t cycles = 0, last_acc = 0;
struct Resp { uint64_t t; uint32_t d; };
static std::deque<Resp> rq;
static uint32_t pl_last = 0xFFFFFFFF, sl_last = 0xFFFFFFFF;
static int pl_cnt = 0, sl_cnt = 0;

static uint8_t sd(size_t a) { return a < sdram.size() ? sdram[a] : 0; }
static uint32_t gd32(uint32_t a) {
    uint32_t v = 0;
    for (int i = 0; i < 4; i++) v = (v << 8) | (a + i < gfx.size() ? gfx[a + i] : 0);
    return v;
}

static void tick() {
    // program ROM ports: ok (and the byte) +promlat clocks after the request
    // appears; garbage before ok, so an early capture shows
    if (top->o_prom_req) {
        uint32_t a = top->o_prom_addr;
        if (a != pl_last) { pl_last = a; pl_cnt = 0; } else if (pl_cnt < promlat) pl_cnt++;
        bool ok = pl_cnt >= promlat;
        top->i_prom_data = ok ? sd(a) : 0xA5;
        top->i_prom_ok = ok;
    } else { pl_last = 0xFFFFFFFF; top->i_prom_ok = 0; }
    if (top->o_srom_req) {
        uint32_t a = top->o_srom_addr;
        if (a != sl_last) { sl_last = a; sl_cnt = 0; } else if (sl_cnt < promlat) sl_cnt++;
        bool ok = sl_cnt >= promlat;
        top->i_srom_data = ok ? sd(a) : 0x5A;
        top->i_srom_ok = ok;
    } else { sl_last = 0xFFFFFFFF; top->i_srom_ok = 0; }
    bool rv = !rq.empty() && rq.front().t <= cycles;
    top->i_rom_rv = rv;
    if (rv) { top->i_rom_data = rq.front().d; rq.pop_front(); }
    bool gnt = cycles - last_acc >= (uint64_t)intv;
    top->i_rom_gnt = gnt;
    top->clk = 0; top->eval();
    if (gnt && top->o_rom_req) {
        rq.push_back({cycles + (uint64_t)lat, gd32(top->o_rom_addr)});
        last_acc = cycles;
    }
    top->clk = 1; top->eval();
    cycles++;
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
    top = std::make_unique<Vd8_sys>();
    std::string setn = plus("set", ""), sdf = plus("sdram", ""), gff = plus("gfx", ""), out = plus("out", ".");
    std::string capf = plus("cap", "");
    SetInfo si;
    if (!set_info(setn, si)) { fprintf(stderr, "unknown set %s\n", setn.c_str()); return 2; }
    long nframes = atol(plus("frames", "600").c_str());
    lat = atoi(plus("lat", "9").c_str());
    intv = atoi(plus("intv", "8").c_str());
    promlat = atoi(plus("promlat", "9").c_str());
    long pause_f = -1, pause_n = 0;
    {
        std::string ps = plus("pause", "");
        if (!ps.empty()) sscanf(ps.c_str(), "%ld:%ld", &pause_f, &pause_n);
    }
    {
        std::ifstream f(sdf, std::ios::binary);
        if (!f) { fprintf(stderr, "cannot open sdram %s\n", sdf.c_str()); return 2; }
        sdram.assign(std::istreambuf_iterator<char>(f), {});
        std::ifstream g(gff, std::ios::binary);
        if (!g) { fprintf(stderr, "cannot open gfx %s\n", gff.c_str()); return 2; }
        gfx.assign(std::istreambuf_iterator<char>(g), {});
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
        top->i_coin = ports[4]; top->i_dsw0 = ports[5]; top->i_dsw1 = ports[6];
    };
    top->i_machine = si.machine;
    top->i_srdb = si.srdb;
    top->i_pause = 0;
    top->i_an0 = 0; top->i_an1 = 0;
    apply_ports();
    top->rst_n = 0;
    top->i_mcu_we = 0;
    top->i_snd_we = 0;
    for (int i = 0; i < 300; i++) tick();
    for (int a = 0; a < 4096; a++) {
        top->i_mcu_addr = a; top->i_mcu_din = sd(0x080000 + a); top->i_mcu_we = 1;
        tick();
    }
    top->i_mcu_we = 0;
    for (int a = 0; a < 32768; a++) {
        top->i_snd_addr = a; top->i_snd_din = sd(0x068000 + a); top->i_snd_we = 1;
        tick();
    }
    top->i_snd_we = 0;
    for (int i = 0; i < 300; i++) tick();
    top->rst_n = 1;
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
        bool am = r->d8_sys__DOT__at_m, as = r->d8_sys__DOT__at_s;
        int line = r->d8_sys__DOT__u_video__DOT__vcnt, hp = r->d8_sys__DOT__u_video__DOT__hcnt;
        if (fbus && frame >= bt0 && frame < bt1 && r->d8_sys__DOT__cen_E) {
            fprintf(fbus, "%ld %d %d main %04x %c %02x\n", frame, line, hp, r->d8_sys__DOT__m_a,
                    r->d8_sys__DOT__m_rnw ? 'R' : 'W', r->d8_sys__DOT__m_rnw ? r->d8_sys__DOT__m_di : r->d8_sys__DOT__m_do);
            if (mach == LM)
                fprintf(fbus, "%ld %d %d sub %04x %c %02x\n", frame, line, hp, r->d8_sys__DOT__s_a,
                        r->d8_sys__DOT__s_rnw ? 'R' : 'W', r->d8_sys__DOT__s_rnw ? r->d8_sys__DOT__s_di : r->d8_sys__DOT__s_do);
        }
        if (ftr && frame >= tr0 && frame < tr1) {
            if (am && r->d8_sys__DOT__m_op && r->d8_sys__DOT__m_rnw)
                fprintf(ftr, "%ld %d %d main %04x\n", frame, line, hp, r->d8_sys__DOT__m_a);
            if (as && r->d8_sys__DOT__s_op && r->d8_sys__DOT__s_rnw)
                fprintf(ftr, "%ld %d %d sub %04x\n", frame, line, hp, r->d8_sys__DOT__s_a);
        }
        for (int c = 0; c < 2; c++) {
            bool a_on = c ? as : am;
            if (!a_on) continue;
            unsigned a = c ? r->d8_sys__DOT__s_a : r->d8_sys__DOT__m_a;
            bool rnw = c ? r->d8_sys__DOT__s_rnw : r->d8_sys__DOT__m_rnw;
            unsigned d = c ? r->d8_sys__DOT__s_do : r->d8_sys__DOT__m_do;
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
            if (fsnd && top->o_snd_wr)
                fprintf(fsnd, "%.12f,%ld,L,%x,%x\n", t, frame, mach == LM ? 0x180c : mach == GO ? 0x3810 : 0x2000,
                        top->o_snd_data);
            if (fstr && frame >= st0 && frame < st1 && r->d8_sys__DOT__u_snd__DOT__cpu_cen) {
                static bool pf = false; static unsigned pfa = 0xFFFFFFFF;
                bool f = r->d8_sys__DOT__u_snd__DOT__fetch && r->d8_sys__DOT__u_snd__DOT__rd;
                unsigned a = r->d8_sys__DOT__u_snd__DOT__A;
                if (f && (!pf || a != pfa)) fprintf(fstr, "%.9f,%x,%x\n", t, a, r->d8_sys__DOT__u_snd__DOT__din);
                pf = f; pfa = a;
            }
            if (fsnd && r->d8_sys__DOT__u_snd__DOT__cpu_cen) {
                unsigned a = r->d8_sys__DOT__u_snd__DOT__A;
                bool rdn = r->d8_sys__DOT__u_snd__DOT__rd && !r->d8_sys__DOT__u_snd__DOT__wr;
                unsigned ym = mach == LM ? 0x0800 : 0x2000, opl = mach == LM ? 0x1000 : 0x4000, lat = mach == LM ? 0x3000 : 0x6000;
                if (r->d8_sys__DOT__u_snd__DOT__wev) {
                    unsigned d = r->d8_sys__DOT__u_snd__DOT__dout;
                    if ((a & ~1u) == ym) fprintf(fsnd, "%.12f,%ld,Y,%x,%x\n", t, frame, a, d);
                    else if ((a & ~1u) == opl) fprintf(fsnd, "%.12f,%ld,P,%x,%x\n", t, frame, a, d);
                    else if (a >= 0x0600 && a < 0x8000 && a != lat) fprintf(fsnd, "%.12f,%ld,U,%x,%x\n", t, frame, a + 0x10000, d);
                }
                if (rdn && (!prd || a != pa)) {
                    unsigned d = r->d8_sys__DOT__u_snd__DOT__din;
                    if ((a & ~1u) == ym || (a & ~1u) == opl || a == lat) fprintf(fsnd, "%.12f,%ld,R,%x,%x\n", t, frame, a, d);
                    else if (a >= 0x0600 && a < 0x8000) fprintf(fsnd, "%.12f,%ld,U,%x,%x\n", t, frame, a, d);
                    else if (a == 0xfffa) fprintf(fsnd, "%.12f,%ld,N,%x,%x\n", t, frame, a, d);
                    else if (a == 0xfffe) fprintf(fsnd, "%.12f,%ld,I,%x,%x\n", t, frame, a, d);
                }
                prd = rdn; pa = a;
            }
            if (faud && (cycles - t0) % 2000 == 0) {
                int16_t v[4] = {(int16_t)top->o_fm, (int16_t)top->o_ssg, (int16_t)top->o_opl, (int16_t)top->o_audio};
                fwrite(v, 2, 4, faud);
            }
        }
        bool ce = top->o_ce_pix;
        if (fmcu && r->d8_sys__DOT__mcu_wr && frame >= mt0 && frame < mt1)
            fprintf(fmcu, "%ld %d %d sfr %02x %02x int1 %d int0 %d\n", frame, line, hp, r->d8_sys__DOT__mcu_wa,
                    r->d8_sys__DOT__mcu_wd, r->d8_sys__DOT__int1, r->d8_sys__DOT__int0);
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
                auto &v = r->d8_sys__DOT__u_video__DOT__u_pal__DOT__g_plain__DOT__u_l__DOT__mem;
                std::vector<uint8_t> pal(1024), palx(1024);
                for (int i = 0; i < 1024; i++) { pal[i] = v[i] & 0xFF; palx[i] = v[i] >> 8; }
                dump(base + ".pal", pal.data(), 1024);
                dump(base + ".palx", palx.data(), 1024);
                dumpw(base + ".fix", r->d8_sys__DOT__u_video__DOT__u_fix__DOT__g_plain__DOT__u_l__DOT__mem, 1024, 2048);
                dumpw(base + ".bg", r->d8_sys__DOT__u_video__DOT__u_bg__DOT__g_plain__DOT__u_l__DOT__mem, 1024, 2048);
                dumpw(base + ".sprl", r->d8_sys__DOT__u_video__DOT__u_spr__DOT__g_snap__DOT__u_l__DOT__mem, 1024, 2048);
                dumpw(base + ".sprb", r->d8_sys__DOT__u_video__DOT__u_spr__DOT__g_snap__DOT__g_one__DOT__u_s__DOT__mem, 1024, 2048);
                std::vector<uint8_t> ram(8192), mram(128);
                for (int i = 0; i < 8192; i++) ram[i] = r->d8_sys__DOT__wram[i];
                for (int i = 0; i < 128; i++) mram[i] = r->d8_sys__DOT__u_mcu__DOT__ram[i];
                dump(base + ".ram", ram.data(), ram.size());
                dump(base + ".mcu", mram.data(), mram.size());
                std::vector<uint8_t> sram(1536);
                for (int i = 0; i < 1536; i++) sram[i] = r->d8_sys__DOT__u_snd__DOT__ram[i];
                dump(base + ".snd", sram.data(), sram.size());
                FILE *fr = fopen((base + ".regs").c_str(), "w");
                fprintf(fr, "bank %d m_irq %d m_firq %d s_irq %d s_firq %d int0 %d int1 %d\n",
                        r->d8_sys__DOT__bank, r->d8_sys__DOT__m_irq, r->d8_sys__DOT__m_firq,
                        r->d8_sys__DOT__s_irq, r->d8_sys__DOT__s_firq, r->d8_sys__DOT__int0, r->d8_sys__DOT__int1);
                fclose(fr);
            }
            if (frame % 500 == 0) {
                printf("vblank %ld overruns %d maxcyc %d verr %d promlate %d unmapped %d xacc %d sndunm %d\n", frame,
                       top->o_dbg_overruns, top->o_dbg_maxcyc, top->o_dbg_verr, top->o_dbg_prom_late,
                       top->o_dbg_unmapped, top->o_dbg_xacc, top->o_dbg_snd_unmapped);
                fflush(stdout);
            }
        }
    }
    printf("DONE vblanks %ld cycles %llu overruns %d maxcyc %d verr %d promlate %d unmapped %d xacc %d sndunm %d\n", frame,
           (unsigned long long)cycles, top->o_dbg_overruns, top->o_dbg_maxcyc, top->o_dbg_verr,
           top->o_dbg_prom_late, top->o_dbg_unmapped, top->o_dbg_xacc, top->o_dbg_snd_unmapped);
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
