// R17 unit test: jt65c02 ADC/SBC results and cycle counts in binary and
// decimal mode against the Rockwell R65C02 data sheet (p. 1-11: ADC/SBC
// imm 2, zp 3; "+1 in decimal mode"). cen every clock: one bus cycle = 4 clk.
module tb_6502;
  logic clk = 0, rst = 1;
  logic [7:0] mem [0:65535];
  wire [15:0] addr; wire [7:0] dout; wire wr, rd, fetch;
  logic [7:0] din;
  always #1 clk = ~clk;
  assign din = mem[addr];
  always @(posedge clk) if (wr) mem[addr] <= dout;
  jt65c02 #(.DECO222(1)) u_cpu (.rst(rst), .clk(clk), .cen(1'b1), .irq(1'b0), .nmi(1'b0),
    .opdec(1'b0), .wr(wr), .rd(rd), .fetch(fetch), .addr(addr), .din(din), .dout(dout));
  integer clkn = 0, i;
  integer seen [0:65535];
  always @(posedge clk) begin
    clkn <= clkn + 1;
    if (!rst && fetch && rd && seen[addr] < 0) seen[addr] <= clkn;
  end
  initial begin
    for (i = 0; i < 65536; i++) begin mem[i] = 8'hEA; seen[i] = -1; end
    // program (see cputest/README)
    {mem['h200],mem['h201],mem['h202],mem['h203],mem['h204],mem['h205],mem['h206],mem['h207]} =
      {8'hD8,8'h18,8'hA9,8'h15,8'h69,8'h27,8'h85,8'h10};
    {mem['h208],mem['h209],mem['h20A],mem['h20B],mem['h20C],mem['h20D],mem['h20E],mem['h20F]} =
      {8'hF8,8'h18,8'hA9,8'h15,8'h69,8'h27,8'h85,8'h11};
    {mem['h210],mem['h211],mem['h212],mem['h213],mem['h214],mem['h215],mem['h216],mem['h217]} =
      {8'h38,8'hA9,8'h42,8'hE9,8'h15,8'h85,8'h12,8'hD8};
    {mem['h218],mem['h219],mem['h21A],mem['h21B],mem['h21C],mem['h21D],mem['h21E],mem['h21F]} =
      {8'h38,8'hA9,8'h42,8'hE5,8'h20,8'h85,8'h13,8'hF8};
    {mem['h220],mem['h221],mem['h222],mem['h223],mem['h224],mem['h225],mem['h226]} =
      {8'h18,8'h65,8'h20,8'h85,8'h14,8'hD8,8'h4C};
    {mem['h227],mem['h228]} = {8'h26,8'h02};
    mem['h20] = 8'h15;
    mem['hFFFC] = 8'h00; mem['hFFFD] = 8'h02;
    repeat (20) @(posedge clk);
    rst = 0;
    repeat (2000) @(posedge clk);
    $display("RES binary ADC #  : 15+27 = %02x (expect 3C)", mem['h10]);
    $display("RES decimal ADC # : 15+27 = %02x (expect 42)", mem['h11]);
    $display("RES decimal SBC # : 42-15 = %02x (expect 27)", mem['h12]);
    $display("RES binary SBC zp : 42-15 = %02x (expect 2D)", mem['h13]);
    $display("RES decimal ADC zp: 2D+15 = %02x (expect 2D+15 BCD-adjusted per 65C02)", mem['h14]);
    $display("CYC binary  ADC #  %0d (ds 2)", (seen['h206]-seen['h204])/4);
    $display("CYC decimal ADC #  %0d (ds 3)", (seen['h20E]-seen['h20C])/4);
    $display("CYC decimal SBC #  %0d (ds 3)", (seen['h215]-seen['h213])/4);
    $display("CYC binary  SBC zp %0d (ds 3)", (seen['h21D]-seen['h21B])/4);
    $display("CYC decimal ADC zp %0d (ds 4)", (seen['h223]-seen['h221])/4);
    $display("CYC binary  LDA #  %0d (ds 2)", (seen['h204]-seen['h202])/4);
    $display("CYC binary  STA zp %0d (ds 3)", (seen['h208]-seen['h206])/4);
    $display("PAIR binary  ADC#+STA zp %0d (ds 5)", (seen['h208]-seen['h204])/4);
    $display("PAIR decimal ADC#+STA zp %0d (ds 6)", (seen['h210]-seen['h20C])/4);
    $display("PAIR decimal SBC#+STA zp %0d (ds 6)", (seen['h217]-seen['h213])/4);
    $display("PAIR binary  SBCzp+STA zp %0d (ds 6)", (seen['h21F]-seen['h21B])/4);
    $display("PAIR decimal ADCzp+STA zp %0d (ds 7)", (seen['h225]-seen['h221])/4);
    $finish;
  end
endmodule
