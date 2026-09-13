# New World Capture

Tools to record one New World session on Linux: the capture CLI, the shared web
controls and the resulting ZIP. English only.

## Start here

- [Capture session quickstart](docs/QUICKSTART.md): one-time setup, then START/STOP per session.
- [Local and remote setup](docs/SETUP.md): Steam/Proton, dependencies and the web service.
- [Web application](Tools/nw_capture/web/README.md): START/STOP, environment variables, storage and security.
- [Capture CLI](Tools/nw_capture/README.md): attach modes, cleanup and limitations.
- [External references and attribution](docs/REFERENCES.md).

From this directory, after installing the dependencies in the setup guide:

```sh
bash Tools/nw_capture/web/run.sh
```

Open `http://127.0.0.1:8787`. The game must already be running. This command is
for capture controls, not game launch. Capture data is shared across browser tabs.
The ZIP contains the ledger, the metadata and, when video is enabled, the recording.

## Scope and data

`Tools/` includes our modified capture stack, Proton launcher, optional local
login helper, web service and experimental offline decoder.
`docs/` contains the setup and quickstart notes.
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
```

Node executes TypeScript directly; these commands do not perform static type checking.
Mocked tests do not establish live game compatibility or anti-cheat safety.

## License

AGPL-3.0, preserving the upstream license in [LICENSE](LICENSE). Capture and decoding
components derive from [Coldzer0/Aeternum-World](https://github.com/Coldzer0/Aeternum-World)
and include our local changes. See [attribution](docs/REFERENCES.md); this is not a
claim that all code or game data was originally authored by us.
