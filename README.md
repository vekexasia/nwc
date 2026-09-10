# New World Capture

Standalone workspace for our New World capture tools, shared web controls,
YouTube integration and offline protocol experiments. English only.

## Start here

- [Resume the previous session](docs/NEXT_SESSION.md): goals, findings, corrected results and next steps.

- [Local and remote setup](docs/SETUP.md): Steam/Proton, dependencies, Sunshine/Moonlight and web service.
- [Web application](Tools/nw_capture/web/README.md): START/STOP, environment variables, storage and security.
- [YouTube OAuth setup](Tools/nw_capture/web/YOUTUBE.md): one-time authorization, unlisted broadcasts and recovery.
- [Capture CLI](Tools/nw_capture/README.md): attach modes, cleanup and limitations.
- [Offline position experiment](docs/Network/offline-position-proof.md): the original rejection-first diagnostic, superseded by the decoders below.
- [ALC protocol reference](docs/Network/alc-protocol-reference.md): message layers, readers, the 48 ALC fields and the world position encoding.
- [Decoder state snapshot](docs/Network/decoder-state.md): where the decoding stands, artifacts, next steps and gotchas.
- [Ghidra workflow](docs/Network/ghidra-workflow.md): measured costs, batching, and the PyGhidra session wrapper.
- [External references and attribution](docs/REFERENCES.md).
- [Workspace handoff](docs/HANDOFF.md): completed background-workflow import and current deployment.

From this directory, after installing the dependencies in the setup guide:

```sh
bash Tools/nw_capture/web/run.sh
```

Open `http://127.0.0.1:8787`. The game must already be running. This command is
for capture controls, not game launch. Capture data is shared across browser tabs.
The ZIP contains metadata, optional raw capture and a YouTube link, never the MKV.
Local backup video remains on the gaming host.

## Scope and data

`Tools/` includes our modified capture stack, Proton launcher, optional local
login helper, web service, OAuth setup and experimental offline decoder.
`docs/` contains our setup, research and verification notes.
Our local capture data is copied into `Tools/nw_capture/captures/` and gitignored.
Those files can contain sensitive decrypted traffic: keep them private.

External Catalog/game dumps, First Light source, NWDB assets and the other user's
Hive capture are **not** included. Refer to their sources instead. No OAuth tokens,
SSH keys or Steam profiles were imported. Runtime dependencies, including the
checksum-verified Frida server, are installed locally but excluded from Git.

This repository has independent Git metadata, no inherited history and no remote.
The original workspace and running gaming-host service were not moved or stopped.

## Checks (no game or live service needed)

```sh
.venv-capture/bin/python -m unittest discover -s Tools/nw_capture -p 'test_*.py'
.venv-capture/bin/python -m unittest discover -s Tools/nw_capture/web -p 'test_*.py'
.venv-capture/bin/python Tools/test_login_new_world.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/test_decode_saved_position.py
node Tools/nw_capture/web/test.ts
CAPTURE_TEST_YOUTUBE=1 node Tools/nw_capture/web/test.ts
node Tools/nw_capture/web/test_youtube.ts
```

Node executes TypeScript directly; these commands do not perform static type checking.
Mocked tests do not establish live game compatibility or anti-cheat safety.

## License

AGPL-3.0, preserving the upstream license in [LICENSE](LICENSE). Capture and decoding
components derive from [Coldzer0/Aeternum-World](https://github.com/Coldzer0/Aeternum-World)
and include our local changes. See [attribution](docs/REFERENCES.md); this is not a
claim that all code or game data was originally authored by us.
