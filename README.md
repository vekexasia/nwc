# New World Capture

Capture a New World session on Linux from a local web page. Each completed
session produces a ZIP containing network data, metadata and, when enabled,
gameplay video.

## Requirements

- Linux with Steam and New World installed.
- Node.js 22.18 or newer.
- Python 3 with `venv`.
- Windows x64 Frida server 17.9.10, matching the Python client. It is not
  bundled; the setup script downloads it.
- `gpu-screen-recorder` when recording video.

## Set up

Follow the one-time [setup guide](docs/QUICKSTART.md), then run from the
repository root:

```sh
bash Tools/nw_capture/setup.sh
```

The script prepares the local capture environment and reports anything still
missing.

## Capture a session

1. Start Steam and New World, then enter the world.
2. Start the capture server from the repository root:
   ```sh
   bash Tools/nw_capture/web/run.sh
   ```
   To capture without video, use:
   ```sh
   CAPTURE_VIDEO=0 bash Tools/nw_capture/web/run.sh
   ```
3. Open <http://127.0.0.1:8787>.
4. Confirm the host checks are OK, enter a session name and select **START**.
5. Wait for the page to show `RUNNING` and confirm the counters are increasing.
6. When finished, select **STOP** before closing the game.
7. Wait for the ZIP download to complete, then stop the server with Ctrl+C.

Closing or reopening the browser does not stop an active capture.

## Output and privacy

Captures remain under `Tools/nw_capture/captures/` and are ignored by Git.
The downloaded ZIP contains:

- `metadata.json`: session details and capture counters.
- `ledger.bin`: captured network data.
- `gameplay.mkv`: gameplay video, when video recording is enabled.

Capture files can contain sensitive traffic. Keep them private and do not
commit or publish them.

## Documentation

- [Capture session quickstart](docs/QUICKSTART.md)
- [Local and remote setup](docs/SETUP.md)
- [Web controls and configuration](Tools/nw_capture/web/README.md)
- [Capture CLI and offline tools](Tools/nw_capture/README.md)

## Checks

These checks do not start the game or a live capture service:

```sh
.venv-capture/bin/python -m unittest discover -s Tools/nw_capture -p 'test_*.py'
.venv-capture/bin/python -m unittest discover -s Tools/nw_capture/web -p 'test_*.py'
.venv-capture/bin/python Tools/test_login_new_world.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/test_decode_saved_position.py
node Tools/nw_capture/web/test.ts
node Tools/nw_capture/web/test_app.ts
```

## License

[AGPL-3.0](LICENSE). Capture and decoding components derive from
[Coldzer0/Aeternum-World](https://github.com/Coldzer0/Aeternum-World). See
[external references and attribution](docs/REFERENCES.md).
