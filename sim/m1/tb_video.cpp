// M1 frame-replay harness for d8_video (Verilator, C++), after the Tecmo 16
// and 1945k III harnesses.
//
// For each frame file in the list: with the pixel enable stopped at the
// start of line 248 (vblank), write the palette, fix RAM and bg RAM through
// the CPU byte port, write the dumped sprite buffer into sprite RAM and copy
// it (so the renderer's buffer holds the dump), then write the live sprite
// RAM, set the scroll bytes and flip, and run one whole frame (272 lines of
// 384 pixels from line 248), capturing every o_de pixel. Mid-scan writes
// listed in the file are applied through the CPU port when the beam reaches
// their (line, hcnt) (MAME's 384 x 272 beam = these counters).
//
// Frame file (.d8f, written by sim/m1/replay.py), little-endian numbers:
//   "D8F1", machine u8 (0 lastmisn, 1 gondo, 2 srdarwin), flags u8 (bit 0
//   flip), nwrites u32, scroll u8 x 4 (MAME m_scroll[0..3]), pad u16;
//   palette 1024, palette ext 1024, fix RAM 2048, bg RAM 2048, sprite
//   buffer 2048, live sprite RAM 2048 bytes;
//   then nwrites x {line u16, hcnt u16, target u8, data u8, addr u16};
//   target 0 palette, 1 palette ext, 2 fix, 3 bg, 4 sprite RAM, 5 sprite
//   buffer copy, 8-11 scroll byte 0-3, 16 flip (data bit 0).
// Output: <out> 256 x 240 x 3 bytes (RGB) and <out>.pen 256 x 240 u16
// (palette index of each pixel, o_dbg_pen).
//
// Plusargs: +sdram=FILE (gfx.bin) +list=FILE (lines "in out"); ROM model:
// pipelined, in order, one request accepted every +intv=N clocks (default
// 8), data +lat=N clocks after acceptance (default 9): the Dooyong M1
// pessimistic port.

#include "Vd8_video.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <memory>
#include <string>
#include <vector>
#include <unistd.h>

static std::unique_ptr<Vd8_video> top;
static std::vector<uint8_t> sdram;
static int lat = 9, intv = 8;
static uint64_t cycles = 0, last_acc = 0;
struct Resp { uint64_t t; uint32_t d; };
static std::deque<Resp> rq;

static uint32_t rd32(uint32_t a) {
    uint32_t v = 0;
    for (int i = 0; i < 4; i++) v = (v << 8) | (a + i < sdram.size() ? sdram[a + i] : 0);
    return v;
}

static void tick(bool ce) {
    top->ce_pix = ce;
    bool rv = !rq.empty() && rq.front().t <= cycles;
    top->i_rom_rv = rv;
    if (rv) { top->i_rom_data = rq.front().d; rq.pop_front(); }
    bool gnt = cycles - last_acc >= (uint64_t)intv;
    top->i_rom_gnt = gnt;
    top->clk = 0; top->eval();
    if (gnt && top->o_rom_req) {
        rq.push_back({cycles + (uint64_t)lat, rd32(top->o_rom_addr)});
        last_acc = cycles;
    }
    top->clk = 1; top->eval();
    cycles++;
}

static void run_pixel() {
    for (int i = 0; i < 15; i++) tick(false);
    tick(true);
}

static std::string plus(const char *name, const char *def) {
    const char *v = Verilated::commandArgsPlusMatch(name);
    if (!v || !*v) return def;
    const char *eq = strchr(v, '=');
    return eq ? std::string(eq + 1) : std::string(def);
}

static void clear_we() {
    top->i_pal_we = top->i_palx_we = top->i_fix_we = top->i_bg_we = top->i_spr_we = 0;
    top->i_spr_copy = top->i_scr_we = top->i_flip_we = 0;
}

static void wait_idle() { while (top->o_busy || top->o_hold) tick(false); }

// one CPU byte write (a 6809 bus cycle is far longer than the hold window,
// so waiting for o_hold here never changes what the RTL sees)
static void wr1(int target, int a, uint8_t d) {
    while (top->o_hold) tick(false);
    top->i_cpu_addr = a & 0x7FF;
    top->i_cpu_din = d;
    switch (target) {
        case 0: top->i_pal_we = 1; break;
        case 1: top->i_palx_we = 1; break;
        case 2: top->i_fix_we = 1; break;
        case 3: top->i_bg_we = 1; break;
        case 4: top->i_spr_we = 1; break;
        case 5: top->i_spr_copy = 1; break;
        case 16: top->i_flip_we = 1; break;
        default:
            if (target >= 8 && target <= 11) { top->i_scr_we = 1; top->i_scr_sel = target - 8; }
    }
    tick(false);
    clear_we();
}

static void wrblk(int target, const uint8_t *p, int n) {
    for (int a = 0; a < n; a++) wr1(target, a, p[a]);
}

static uint16_t le16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t le32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    top = std::make_unique<Vd8_video>();
    std::string sd = plus("sdram", ""), list = plus("list", "");
    lat = atoi(plus("lat", "9").c_str());
    intv = atoi(plus("intv", "8").c_str());
    last_acc = (uint64_t)-1000;
    {
        std::ifstream f(sd, std::ios::binary);
        if (!f) { fprintf(stderr, "cannot open sdram %s\n", sd.c_str()); return 2; }
        sdram.assign(std::istreambuf_iterator<char>(f), {});
    }
    std::vector<std::pair<std::string, std::string>> frames;
    {
        std::ifstream f(list);
        std::string a, b;
        while (f >> a >> b) frames.push_back({a, b});
    }
    if (frames.empty()) { fprintf(stderr, "empty list\n"); return 2; }

    const size_t HDR = 4 + 2 + 4 + 4 + 2, RAMS = 1024 + 1024 + 4 * 2048;
    std::vector<uint8_t> fb;
    auto load = [&](const std::string &p) {
        std::ifstream f(p, std::ios::binary);
        fb.assign(std::istreambuf_iterator<char>(f), {});
        return fb.size() >= HDR + RAMS && memcmp(fb.data(), "D8F1", 4) == 0;
    };
    if (!load(frames[0].first)) { fprintf(stderr, "bad frame %s\n", frames[0].first.c_str()); return 2; }
    top->i_machine = fb[4];
    top->rst_n = 0;
    clear_we();
    for (int i = 0; i < 16; i++) tick(false);
    top->rst_n = 1;
    tick(false);
    // counters are at the start of line 248 (the first vblank line)

    int bad = 0;
    for (auto &fr : frames) {
        if (!load(fr.first)) { fprintf(stderr, "bad frame %s\n", fr.first.c_str()); return 2; }
        if (fb[4] != top->i_machine) { fprintf(stderr, "machine changes within a list\n"); return 2; }
        const uint32_t nw = le32(&fb[6]);
        const uint8_t *sc = &fb[10];
        const uint8_t *ram = &fb[HDR];
        const uint8_t *wl = ram + RAMS;
        if (fb.size() < HDR + RAMS + (size_t)nw * 8) { fprintf(stderr, "short %s\n", fr.first.c_str()); return 2; }
        wait_idle();
        uint16_t over0 = top->o_dbg_overruns;
        wrblk(0, ram, 1024);
        wrblk(1, ram + 1024, 1024);
        wrblk(2, ram + 2048, 2048);
        wrblk(3, ram + 4096, 2048);
        wrblk(4, ram + 6144, 2048);                 // the dumped buffer ...
        wr1(5, 0, 0);                               // ... copied into the buffer
        wait_idle();
        wrblk(4, ram + 8192, 2048);                 // then the live sprite RAM
        for (int k = 0; k < 4; k++) wr1(8 + k, 0, sc[k]);
        wr1(16, 0, fb[5] & 1);

        std::vector<uint8_t> out;
        std::vector<uint16_t> pen;
        out.reserve(256 * 240 * 3);
        pen.reserve(256 * 240);
        uint32_t wi = 0;
        for (long i = 0; i < 272L * 384; i++) {
            long line = (248 + i / 384) % 272, h = i % 384;
            while (wi < nw) {
                const uint8_t *w = wl + 8 * wi;
                if (le16(w) != line || le16(w + 2) != h) break;
                wr1(w[4], le16(w + 6), w[5]);
                wi++;
            }
            run_pixel();
            if (top->o_de) {
                out.push_back(top->o_r);
                out.push_back(top->o_g);
                out.push_back(top->o_b);
                pen.push_back(top->o_dbg_pen);
            }
        }
        if (wi != nw) { fprintf(stderr, "%s: applied %u of %u writes\n", fr.first.c_str(), wi, nw); bad++; }
        if (out.size() != 256u * 240 * 3) {
            fprintf(stderr, "%s: captured %zu pixels\n", fr.first.c_str(), out.size() / 3);
            bad++;
        }
        {
            std::ofstream o(fr.second, std::ios::binary);
            o.write((const char *)out.data(), out.size());
            std::ofstream op(fr.second + ".pen", std::ios::binary);
            op.write((const char *)pen.data(), pen.size() * 2);
        }
        printf("FRAME %s overruns %d maxcyc %d err %d\n", fr.first.c_str(),
               (int)(uint16_t)(top->o_dbg_overruns - over0), (int)top->o_dbg_maxcyc, (int)top->o_dbg_err);
    }
    printf("DONE frames %zu bad %d cycles %llu\n", frames.size(), bad, (unsigned long long)cycles);
    top->final();
    top.reset();
    fflush(stdout);
    _exit(bad ? 1 : 0);
}
