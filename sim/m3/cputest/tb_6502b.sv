// R17 unit test 2: cycle counts of addressing modes in the key-off path,
// each instruction followed by NOP (2); measured opcode fetch to the fetch
// after the NOP, minus 2. Data sheet: Rockwell R65C02 matrix p. 1-11.
module tb_6502b;
  logic clk = 0, rst = 1;
  logic [7:0] mem [0:65535];
  wire [15:0] addr; wire [7:0] dout; wire wr, rd, fetch;
  wire [7:0] din = mem[addr];
  always #1 clk = ~clk;
  always @(posedge clk) if (wr) mem[addr] <= dout;
  jt65c02 #(.DECO222(1)) u_cpu (.rst(rst), .clk(clk), .cen(1'b1), .irq(1'b0), .nmi(1'b0),
    .opdec(1'b0), .wr(wr), .rd(rd), .fetch(fetch), .addr(addr), .din(din), .dout(dout));
  integer clkn = 0, i, pc;
  integer seen [0:65535];
  always @(posedge clk) begin
    clkn <= clkn + 1;
    if (!rst && fetch && rd && seen[addr] < 0) seen[addr] <= clkn;
  end
  // emit: instruction bytes then NOP; record start address
  integer starts [0:31]; integer nstart = 0;
  task emit(input [7:0] b0, input [7:0] b1, input [7:0] b2, input integer len);
    begin
      starts[nstart] = pc; nstart = nstart + 1;
      mem[pc] = b0; if (len > 1) mem[pc+1] = b1; if (len > 2) mem[pc+2] = b2;
      pc = pc + len; mem[pc] = 8'hEA; pc = pc + 1;
    end
  endtask
  initial begin
    for (i = 0; i < 65536; i++) begin mem[i] = 8'hEA; seen[i] = -1; end
    pc = 'h0300;
    emit(8'hA2, 8'h05, 0, 2);          // 0 ldx #$05            ds 2
    emit(8'hA0, 8'h10, 0, 2);          // 1 ldy #$10            ds 2
    emit(8'hBD, 8'h00, 8'h40, 3);      // 2 lda $4000,x no cross ds 4
    emit(8'hBD, 8'hFE, 8'h40, 3);      // 3 lda $40FE,x cross    ds 5
    emit(8'h9D, 8'h00, 8'h41, 3);      // 4 sta $4100,x          ds 5
    emit(8'h9D, 8'hFE, 8'h41, 3);      // 5 sta $41FE,x cross    ds 5
    emit(8'hDE, 8'h00, 8'h42, 3);      // 6 dec $4200,x          ds 7
    emit(8'hDE, 8'hFE, 8'h42, 3);      // 7 dec $42FE,x cross    ds 7
    emit(8'hB1, 8'h30, 0, 2);          // 8 lda ($30),y no cross ds 5
    emit(8'hB1, 8'h32, 0, 2);          // 9 lda ($32),y cross    ds 6
    emit(8'h91, 8'h30, 0, 2);          // 10 sta ($30),y         ds 6
    emit(8'hA5, 8'h30, 0, 2);          // 11 lda $30             ds 3
    emit(8'hA6, 8'h31, 0, 2);          // 12 ldx $31             ds 3
    emit(8'hC9, 8'h90, 0, 2);          // 13 cmp #$90            ds 2
    emit(8'h0A, 0, 0, 1);              // 14 asl a               ds 2
    emit(8'hAA, 0, 0, 1);              // 15 tax                 ds 2
    // jmp ($0034) -> $0380, at $0380: nop; jmp $0390
    starts[nstart] = pc; nstart = nstart + 1;   // 16 jmp (ind) ds 6 (measured to $0380)
    mem[pc] = 8'h6C; mem[pc+1] = 8'h34; mem[pc+2] = 8'h00;
    mem['h34] = 8'h80; mem['h35] = 8'h03;
    mem['h380] = 8'hEA; mem['h381] = 8'h4C; mem['h382] = 8'h81; mem['h383] = 8'h03; // loop
    mem['h30] = 8'h00; mem['h31] = 8'h44; mem['h32] = 8'hF8; mem['h33] = 8'h44;
    mem['hFFFC] = 8'h00; mem['hFFFD] = 8'h03;
    repeat (20) @(posedge clk);
    rst = 0;
    repeat (4000) @(posedge clk);
    for (i = 0; i < 16; i++)
      $display("T%0d at %04x: %0d cycles", i, starts[i], (seen[starts[i+1]] - seen[starts[i]]) / 4 - 2);
    $display("T16 jmp (ind): %0d cycles", (seen['h380] - seen[starts[16]]) / 4);
    $finish;
  end
endmodule
