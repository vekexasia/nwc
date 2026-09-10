import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class RawListing extends ghidra.app.script.GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address start = toAddr(Long.decode(args[0]));
        long byteCount = args.length > 1 ? Long.decode(args[1]) : 0x60;
        Function stale = getFunctionAt(start);
        if (stale != null) {
            removeFunctionAt(start);
        }
        Address address = start;
        Address end = start.add(byteCount);
        while (address.compareTo(end) < 0) {
            if (getInstructionAt(address) == null) {
                disassemble(address);
            }
            Instruction instruction = getInstructionAt(address);
            if (instruction == null) {
                println(String.format("0x%x: <no instruction>", address.getOffset()));
                address = address.add(1);
                continue;
            }
            println(String.format("0x%x: %-24s %s", instruction.getAddress().getOffset(),
                    instruction.getBytes() == null ? "" : bytes(instruction.getBytes()),
                    instruction));
            address = instruction.getAddress().add(instruction.getLength());
        }
        Function function = getFunctionAt(start);
        println(function == null ? "function: <none>" : "function: " + function.getEntryPoint()
                + " body=" + function.getBody().getNumAddresses());
    }

    private String bytes(byte[] data) {
        StringBuilder result = new StringBuilder();
        for (byte value : data) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02x", value & 0xff));
        }
        return result.toString();
    }
}
