// Minimal driver for jtframe's ucode package (jotego/jtcores a72a4460):
// equivalent to `jtframe ucode --output <out> <module> <file>`.
package main

import (
	"fmt"
	"os"
	"uctool/ucode"
)

func main() {
	if len(os.Args) != 4 {
		fmt.Println("usage: uctool <output> <module> <file>")
		os.Exit(2)
	}
	ucode.Args.Output = os.Args[1]
	if e := ucode.Make(os.Args[2], os.Args[3]); e != nil {
		fmt.Println(e)
		os.Exit(1)
	}
}
