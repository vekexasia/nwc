import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.util.task.ConsoleTaskMonitor;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

// SchemaTable <builderVA>: decompile a schema builder and print its property table
// (bit order, member offset, name, descriptor, reader at descriptor+0x30).
// This replaces the "dump the C and read it" routine with a compact answer.
public class SchemaTable extends ghidra.app.script.GhidraScript {

    private String asciiAt(Memory mem, Address a, int max) {
        try {
            byte[] b = new byte[max];
            int n = mem.getBytes(a, b);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < n; i++) {
                int ch = b[i] & 0xff;
                if (ch == 0) break;
                if (ch < 0x20 || ch > 0x7e) { if (sb.length() == 0) return null; break; }
                sb.append((char) ch);
            }
            return sb.length() >= 2 ? sb.toString() : null;
        } catch (Exception e) { return null; }
    }

    private long qwordAt(Memory mem, Address a) {
        try {
            byte[] b = new byte[8];
            mem.getBytes(a, b);
            long v = 0;
            for (int i = 7; i >= 0; i--) v = (v << 8) | (b[i] & 0xff);
            return v;
        } catch (Exception e) { return -1; }
    }

    private static long parseIndex(String s) {
        return s.startsWith("0x") ? Long.parseLong(s.substring(2), 16) : Long.parseLong(s);
    }

    @Override
    public void run() throws Exception {
        String arg = getScriptArgs()[0];
        Address addr = toAddr(Long.decode(arg));
        Function f = getFunctionAt(addr);
        if (f == null) { println("SchemaTable: no function at " + arg); return; }
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        DecompileResults res = di.decompileFunction(f, 300, new ConsoleTaskMonitor());
        if (!res.decompileCompleted()) { println("SchemaTable: decompile failed"); return; }
        String c = res.getDecompiledFunction().getC();
        Memory mem = currentProgram.getMemory();

        Map<Long, String> descriptor = new LinkedHashMap<>();
        Matcher dm = Pattern.compile("param_1\\[(0x[0-9a-f]+|\\d+)\\]\\s*=\\s*&(UNK_[0-9a-f]+);").matcher(c);
        while (dm.find()) descriptor.put(parseIndex(dm.group(1)) * 8, dm.group(2).substring(4));

        Map<Long, String> names = new LinkedHashMap<>();
        List<Long> order = new ArrayList<>();
        Matcher nm = Pattern.compile("\\*puVar3 = &(UNK_[0-9a-f]+);\\s*\\n\\s*puVar3\\[1\\] = param_1 \\+ (0x[0-9a-f]+|\\d+);").matcher(c);
        while (nm.find()) {
            long off = parseIndex(nm.group(2)) * 8;
            names.put(off, nm.group(1).substring(4));
            order.add(off);
        }

        println("builder " + arg + " -> " + order.size() + " properties, " + descriptor.size() + " descriptor slots");
        println(String.format("%3s %-9s %-26s %-14s %-12s", "bit", "member", "name", "descriptor", "reader"));
        int bit = 0;
        for (Long off : order) {
            String nameVa = names.get(off);
            String label = nameVa == null ? "?" : asciiAt(mem, toAddr(Long.parseLong(nameVa, 16)), 40);
            String desc = descriptor.get(off);
            String reader = "-";
            if (desc != null) {
                long r = qwordAt(mem, toAddr(Long.parseLong(desc, 16)).add(0x30));
                if (r > 0) reader = String.format("0x%x", r);
            }
            println(String.format("%3d +0x%-6x %-26s %-14s %-12s", bit, off,
                    label == null ? "?" : label, desc == null ? "-" : "0x" + desc, reader));
            bit++;
        }
    }
}
