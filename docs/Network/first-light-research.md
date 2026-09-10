# First Light repository research

Research date: 2026-09-10

## Identified repository

The repository matching the requested Amazon New World reverse-engineering/tooling context is:

**`nw-private-server/first-light`**  
https://github.com/nw-private-server/first-light

GitHub's repository API confirms the exact owner/repository, that it is public, that the owner is the `nw-private-server` organization, and that `main` is the default branch:  
https://api.github.com/repos/nw-private-server/first-light

The repository description field is currently null. Its primary source of project description is the README, which titles the project **“New World: First Light”** and says it is a community effort to build a private-server emulator for New World. Its stated MVP is to accept the real unmodified client, pass authentication, and enter a static world. The README explains that “First Light” refers to the former in-game territory:  
https://github.com/nw-private-server/first-light/blob/main/README.md

## What it contains

Based on the repository tree and primary documentation, this is a Python reverse-engineering and protocol/tooling project, not merely a project named after the territory. It contains:

- `server/`: an HTTPS authentication mock, a DTLS/Javelin REP responder, and protocol codecs.
- `tools/`: traffic-capture and runtime-instrumentation tooling, including Frida/client hooks.
- `docs/`: connection-flow, capture, DTLS, GridMate-reference, and protocol documentation.
- `analysis/`: Ghidra/decompilation findings, message inventories, wire-format notes, and state-machine research.
- `info/`: redacted New World captures and type-registry/reference data.

The protocol overview identifies the layers as HTTPS auth, DTLS 1.2/Javelin REP, GridMate Carrier datagrams, and typed application messages. It also identifies the project target as the New World client reaching the in-game state machine:  
https://github.com/nw-private-server/first-light/blob/main/docs/protocol-overview.md

The capture guide confirms that the project reconstructs the server protocol from captured New World traffic, including decrypted Javelin packets, login-to-spawn captures, and future in-world traffic:  
https://github.com/nw-private-server/first-light/blob/main/docs/capture-guide.md

## Current status and caveat

The current README begins with **“THIS REPOSITORY IS DEFUNCT”** and says active development moved to the OpenWorld Discord. Therefore this GitHub repository should be treated as a historical source snapshot, not as the current active development venue:  
https://github.com/nw-private-server/first-light/blob/main/README.md

The project's generated FAQ also states that it is an independent reverse-engineering project and is **not affiliated with Amazon Games**:  
https://github.com/nw-private-server/first-light/blob/main/site/data.json

## Relationship to New World and NWDB

- **New World:** direct and explicit. The README, protocol documents, capture tooling, game-log paths, Javelin/DTLS implementation, and captured message data all target Amazon Games' *New World* client/server protocol.
- **NWDB:** no direct relationship found. A full text search of the downloaded `main` tree found no `nwdb`, `nw-db`, or `nw db` references, and the README/tree show no NWDB dependency or data import. `nwdb.info` is a separate New World database website: https://nwdb.info/
- Consequently, `first-light` is relevant to network/protocol reverse engineering and private-server emulation; it is not an NWDB data-extraction repository and should not be treated as an NWDB component.

## Disambiguation

GitHub name searches for `FirstLight` and `First Light` return multiple unrelated projects. Examples include:

- `321Fetch/FirstLight` — Kotlin project described only as “FirstLight”: https://github.com/321Fetch/FirstLight
- `cruftbox/firstlight` — personal morning newspaper: https://github.com/cruftbox/firstlight
- `monome/firstlight` — norns study project: https://github.com/monome/firstlight
- `MarkMMullin/FirstLight` — VR motion tracking: https://github.com/MarkMMullin/FirstLight

Other New World GitHub projects are related by subject but are not this repository, such as `MontagueM/NewWorldUnpacker` (a `.pak` unpacker) and `Json-x-ly/NewWorldDatasheetDecoder` (CSV game-file decoder):

- https://github.com/MontagueM/NewWorldUnpacker
- https://github.com/Json-x-ly/NewWorldDatasheetDecoder

The exact owner/repository match is therefore **`nw-private-server/first-light`**, not one of the unrelated `FirstLight` name matches or the separate New World data/unpacking tools.

Search pages checked:

- https://github.com/search?q=FirstLight&type=repositories
- https://github.com/search?q=First%20Light&type=repositories
- https://github.com/search?q=NewWorld%20FirstLight&type=repositories
