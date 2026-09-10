# Workspace handoff

## New workspace

`~/git/personale/new-world-capture`

Independent local Git repository on `main`; no remote, commit or push was created.
The old `~/git/personale/Aeternum-World` workspace remains unchanged by this migration.
Tool paths were preserved so relative imports and web-worker paths still resolve.
The new README and SETUP guide are the entry points; older reports retain historical
session names and paths as evidence, not current launch defaults.

## Completed background experiment imported

Workflow `3b9ee3ed-e143-4adc-9750-c538c5b28fd4` completed. Its three finalized
Python files and two proof reports were imported after checking that the new
workspace had no conflicting edits. No additional workflow was started.

Import review caught a missing cursor advance after the explicit two-byte reliable
sequence in `Tools/nw_capture/decode_dtls_ledger.py`. The new workspace fixes it;
a regression failed before the one-line fix and passed afterward. Both saved
ledgers were rerun. The original workflow counts were superseded in both reports.

- [Our capture result](Network/offline-position-proof.md)
- [External Hive comparison](Network/hive-capture-position-proof.md)

The Hive ledger was read at its existing external path, never copied here. Only
aggregate diagnostics were written to gitignored `private/`. No verified coordinates
were recovered. Do not copy the old decoder over the corrected version here.

`private/migration-manifest.json` records the initial snapshot;
`private/hive-workflow-import.json` records the completed import and local fix.
The source workspace and live gaming-host service remain untouched.

## Our data

Local owned capture roots were copied into `Tools/nw_capture/captures/`, excluding
`offline-hive-scratch`. Our historical ZIPs remain private original artifacts;
they may predate the newer link-only ZIP behavior. Standalone keylog files were
excluded from the directory copy, but raw traffic and old archives remain sensitive.

Our Test teleport ledger is available locally at:

`Tools/nw_capture/captures/offline-position-scratch/ledger.bin`

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_saved_position.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin \
  --out-json Tools/nw_capture/captures/offline-position-scratch/new-workspace-diagnostic.json
```

No other player's data, Catalog, upstream raw log or First Light checkout was copied.
No host OAuth/SSH/Steam credentials were copied. Capture files are ignored by Git;
review the explicit file set before staging anything.

## Existing deployment

The running game, Sunshine/Moonlight, SSH tunnel and capture web service were not
changed or restarted. The gaming host still uses its old deployment paths and
private configuration described in `docs/Streaming/new-world-capture.md` and the
historical host section of `Tools/nw_capture/web/YOUTUBE.md`.

Switching that live deployment to this source tree is a separate controlled step:
wait until the operator finishes capture, stop only the owned capture service,
verify cleanup, install source/dependencies at the new host path and reuse the
existing private configuration explicitly. Do not clear owner locks or launch a
second capturer just because the source repository changed.

## Migration verification

Verified directly in the new directory:

- 15 capture tests and 8 web Python tests passed.
- Login-screen assertion checks and offline decoder self-check passed.
- Both Node lifecycle modes and the OAuth client check passed.
- Our Test teleport ledger decoded offline without any dependency on the old
  workspace: 6354 ledger records, 11923 Carrier messages, no verified positions.
- Source Markdown links resolve; private captures, environment and credentials
  are excluded from the Git candidate file list.
- A private .venv-capture contains the pinned capture requirements and optional
  evdev 2.0.0 for local login-helper checks.
- Windows Frida server 17.9.10 was downloaded from the official release, verified
  against its published SHA-256 and installed as a gitignored runtime dependency.
  It was not executed or attached to a game; provenance is in private/frida-provenance.json.
- Static TypeScript type checking and a new live game/streaming-host deployment
  were not performed. Existing datetime deprecation warnings remain.

After the completed import, the offline regression, both saved-ledger reruns,
15 capture tests, 8 web Python tests, both Node lifecycle modes and OAuth checks
passed. This does not establish a working gameplay decoder or live deployment.
