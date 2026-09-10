import ghidra.program.model.listing.Function;
import ghidra.util.task.ConsoleTaskMonitor;

// Prints one line so the cost of opening the project can be measured apart from the work.
public class Ping extends ghidra.app.script.GhidraScript {
    @Override
    public void run() throws Exception {
        println("PING " + currentProgram.getName() + " functions=" + currentProgram.getFunctionManager().getFunctionCount());
    }
}
