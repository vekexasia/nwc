import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Symbol;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.io.PrintWriter;

// Prints the first 8 qwords of each given structure address, labelling code pointers.
public class DumpQwords extends ghidra.app.script.GhidraScript {

    private long qwordAt(Memory mem, Address a) {
        try {
            byte[] b = new byte[8];
            mem.getBytes(a, b);
            long v = 0;
            for (int i = 7; i >= 0; i--) v = (v << 8) | (b[i] & 0xff);
            return v;
        } catch (Exception e) {
            return -1;
        }
    }

    private String label(Address a) {
        Function f = getFunctionAt(a);
        if (f != null) return "FUNC " + f.getName();
        Symbol s = getSymbolAt(a);
        return s != null ? s.getName() : "";
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Memory mem = currentProgram.getMemory();
        PrintWriter w = new PrintWriter(new BufferedWriter(new FileWriter(args[0])));
        for (int k = 1; k < args.length; k++) {
            long base = Long.decode(args[k]);
            w.println(String.format("STRUCT 0x%x", base));
            for (int i = 0; i < 8; i++) {
                Address a = toAddr(base + i * 8L);
                long q = qwordAt(mem, a);
                String lab = "";
                if (q >= 0x140000000L && q < 0x148000000L) lab = label(toAddr(q));
                else if (q >= 0x148000000L && q < 0x150000000L) lab = "(data)";
                w.println(String.format("  +0x%02x = 0x%x %s", i * 8, q, lab));
            }
        }
        w.close();
        println("wrote " + args[0]);
    }
}
