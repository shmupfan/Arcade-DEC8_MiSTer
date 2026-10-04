// d8_rotary unit test (CLK_HZ = 1000: 250-clock first repeat, 100-clock
// repeat). make -f m4.mk m4-rotary
#include "Vd8_rotary.h"
#include <cstdio>
static Vd8_rotary *t;
static int fails = 0;
static void tick(int n = 1) { while (n--) { t->clk = 0; t->eval(); t->clk = 1; t->eval(); } }
static void expect(int pos, const char *what) {
    if (t->o_pos != pos) { printf("FAIL %s: pos %d, expected %d\n", what, t->o_pos, pos); fails++; }
    else printf("ok   %s: pos %d\n", what, pos);
}
int main() {
    t = new Vd8_rotary;
    t->reset = 1; t->i_left = 0; t->i_right = 0; t->i_spinner = 0; t->i_paddle = 0; t->i_spin_div = 8;
    tick(4); t->reset = 0; tick(4);
    expect(0, "reset");
    t->i_right = 1; tick(2); expect(11, "turn right press (0 -> 11, MAME increment lowers)");
    tick(240); expect(11, "held 242 clocks, no repeat yet");
    tick(20); expect(10, "first repeat at 250");
    tick(100); expect(9, "second repeat 100 later");
    t->i_right = 0; tick(5);
    t->i_left = 1; tick(2); expect(10, "turn left press");
    t->i_left = 0; tick(2); t->i_left = 1; tick(2); expect(11, "left again");
    t->i_left = 0; tick(2); t->i_left = 1; tick(2); expect(0, "left wraps 11 -> 0");
    t->i_left = 0; tick(2);
    t->i_right = 1; t->i_left = 1; tick(400); expect(0, "both held: no turn");
    t->i_right = 0; t->i_left = 0; tick(2);
    // spinner: +5 then +5 (toggle) -> 10 counts -> one cw step, 2 left over
    t->i_spinner = 0x005 | 0x100; tick(3); t->i_spinner = 0x005; tick(3); expect(11, "spinner +10 counts: one step right");
    t->i_spinner = (0x100 | (uint8_t)(-12)); tick(5); expect(0, "spinner -12 (acc -10): one step left");
    // paddle: 128 -> 11 - 6 = 5
    t->i_paddle = 128; tick(4); expect(5, "paddle 128");
    t->i_paddle = 255; tick(4); expect(0, "paddle 255");
    t->i_paddle = 0; tick(4); expect(11, "paddle 0");
    tick(50); expect(11, "paddle still: no change");
    printf(fails ? "FAILED %d\n" : "PASS\n", fails);
    return fails != 0;
}
