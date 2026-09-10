import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.util.task.ConsoleTaskMonitor;

public class Sweep extends ghidra.app.script.GhidraScript {
    @Override
    public void run() throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();
        for (String arg : getScriptArgs()) {
            String[] parts = arg.split(":");
            Address addr = toAddr(Long.decode(parts[0]));
            long window = parts.length > 1 ? Long.decode(parts[1]) : 2048;
            // linear sweep: Ghidra's FlatProgramAPI only disassembles one instruction at a time
            Function stale = getFunctionAt(addr);
            if (stale != null) { removeFunctionAt(addr); println("SWEEP removed stale function at " + arg); }
            Address a = addr;
            long limit = addr.getOffset() + window;
            while (a.getOffset() < limit) {
                if (getInstructionAt(a) == null) disassemble(a);
                Instruction ins = getInstructionAt(a);
                if (ins == null) { a = a.add(1); continue; }
                a = ins.getAddress().add(ins.getLength());
            }
            Function f = getFunctionAt(addr);
            if (f == null) f = createFunction(addr, null);
            boolean swept = getInstructionAt(addr) != null;
            if (f == null) { println("SWEEP " + arg + ": no function"); continue; }
            var res = di.decompileFunction(f, 120, mon);
            var out = res.getDecompiledFunction();
            println("SWEEP " + arg + " -> " + f.getName() + " body=" + f.getBody().getNumAddresses() + " bytes, first-insn-disassembled=" + swept);
            println(out == null ? "<no decompilation>" : out.getC());
        }
        println("SWEEP done");
    }
}
