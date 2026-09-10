import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.io.PrintWriter;

// Dumps every NUL-terminated printable ASCII run in an address range, with its address.
public class DumpStrings extends ghidra.app.script.GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address start = toAddr(Long.decode(args[0]));
        long end = Long.decode(args[1]);
        Memory mem = currentProgram.getMemory();
        PrintWriter w = new PrintWriter(new BufferedWriter(new FileWriter(args[2])));
        long a = start.getOffset();
        while (a < end) {
            Address cur = toAddr(a);
            try {
                byte[] head = new byte[1];
                mem.getBytes(cur, head);
                if ((head[0] & 0xff) < 0x20 || (head[0] & 0xff) > 0x7e) {
                    a++;
                    continue;
                }
                byte[] buf = new byte[256];
                int n = mem.getBytes(cur, buf);
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < n; i++) {
                    int c = buf[i] & 0xff;
                    if (c < 0x20 || c > 0x7e) break;
                    sb.append((char) c);
                }
                if (sb.length() >= 2) w.println(String.format("0x%x  %s", a, sb));
                a += Math.max(sb.length(), 1);
            } catch (Exception e) {
                a++;
            }
        }
        w.close();
        println("wrote " + args[2]);
    }
}
