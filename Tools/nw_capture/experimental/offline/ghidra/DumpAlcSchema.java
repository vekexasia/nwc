import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Symbol;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

// Dumps a function's decompiled C plus every operand that points into a data range,
// resolving each target to its string / pointer / reader slot.
public class DumpAlcSchema extends ghidra.app.script.GhidraScript {

    private String asciiAt(Memory mem, Address a, int max) {
        try {
            byte[] b = new byte[max];
            int n = mem.getBytes(a, b);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < n; i++) {
                int c = b[i] & 0xff;
                if (c == 0) break;
                if (c < 0x20 || c > 0x7e) {
                    if (sb.length() == 0) return null;
                    break;
                }
                sb.append((char) c);
            }
            return sb.length() >= 3 ? sb.toString() : null;
        } catch (Exception e) {
            return null;
        }
    }

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
        if (a == null) return "";
        Function f = getFunctionAt(a);
        if (f != null) return f.getName();
        Symbol s = getSymbolAt(a);
        return s != null ? s.getName() : "";
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address fn = toAddr(Long.decode(args[0]));
        String out = args[1];
        long lo = Long.decode(args.length > 2 ? args[2] : "0x148000000");
        long hi = Long.decode(args.length > 3 ? args[3] : "0x149000000");
        Memory mem = currentProgram.getMemory();
        Listing listing = currentProgram.getListing();
        Function f = getFunctionAt(fn);
        if (f == null) {
            println("NO FUNCTION AT " + fn);
            return;
        }
        PrintWriter w = new PrintWriter(new BufferedWriter(new FileWriter(out)));
        w.println("FUNCTION " + fn + " " + f.getName() + " body " + f.getBody().getMinAddress()
                + ".." + f.getBody().getMaxAddress());

        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        DecompileResults res = di.decompileFunction(f, 300, new ConsoleTaskMonitor());
        w.println("=== DECOMPILED C ===");
        w.println(res.decompileCompleted() ? res.getDecompiledFunction().getC()
                : "DECOMPILE FAILED: " + res.getErrorMessage());

        w.println("=== OPERAND REFERENCES INTO " + Long.toHexString(lo) + ".." + Long.toHexString(hi) + " ===");
        Set<Long> targets = new LinkedHashSet<>();
        InstructionIterator it = listing.getInstructions(f.getBody(), true);
        while (it.hasNext()) {
            Instruction ins = it.next();
            Set<Long> vals = new LinkedHashSet<>();
            for (int i = 0; i < ins.getNumOperands(); i++) {
                for (Object o : ins.getOpObjects(i)) {
                    long v = -1;
                    if (o instanceof Address) v = ((Address) o).getOffset();
                    else if (o instanceof Scalar) v = ((Scalar) o).getUnsignedValue();
                    if (v >= lo && v < hi) vals.add(v);
                }
            }
            if (!vals.isEmpty()) {
                StringBuilder sb = new StringBuilder(ins.getAddress() + "  " + ins + "   ->");
                for (long v : vals) sb.append(String.format(" 0x%x", v));
                w.println(sb.toString());
                targets.addAll(vals);
            }
        }

        w.println("=== TARGETS ===");
        for (long v : targets) {
            Address a = toAddr(v);
            String s = asciiAt(mem, a, 64);
            long q0 = qwordAt(mem, a);
            long q30 = qwordAt(mem, a.add(0x30));
            StringBuilder sb = new StringBuilder(String.format("0x%x", v));
            sb.append(s != null ? ("  STR=\"" + s + "\"") : "");
            if (q0 != 0 && q0 != -1 && q0 >= 0x140000000L && q0 < 0x150000000L) {
                String s2 = asciiAt(mem, toAddr(q0), 48);
                sb.append(String.format("  q0=0x%x", q0)).append(s2 != null ? (" STR2=\"" + s2 + "\"") : "");
            }
            if (q30 >= 0x140000000L && q30 < 0x148000000L) {
                sb.append(String.format("  q30=0x%x", q30)).append(
                        label(toAddr(q30)).isEmpty() ? "" : (" " + label(toAddr(q30))));
            }
            w.println(sb.toString());
        }

        w.println("=== TARGET BLOCKS (qword per 8 bytes) ===");
        for (long v : targets) {
            Address a = toAddr(v);
            StringBuilder sb = new StringBuilder(String.format("0x%x:", v));
            for (int i = 0; i < 16; i++) {
                long q = qwordAt(mem, a.add(i * 8));
                sb.append(String.format(" %x", q));
            }
            w.println(sb.toString());
        }
        w.close();
        println("wrote " + out + " targets=" + targets.size());
    }
}
