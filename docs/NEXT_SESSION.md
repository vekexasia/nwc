# Resume here

This file preserves the conversation handoff. Continue in
`~/git/personale/new-world-capture`, not the old Aeternum-World checkout.

## User's objective

Capture New World while playing locally on Omarchy or remotely through
Sunshine/Moonlight. Use the shared web app for START/STOP, then eventually decode
live player positioning and show a moving map with a trail.

All documentation, code comments and UI should be English. The user requested
this standalone repository with our tools, documentation, setup and own capture
data, referencing external projects rather than bundling their datasets.
Do not start another workflow for this handoff.

## What is already saved and working

- Capture/Proton tooling, optional local login helper, shared web service,
  video/YouTube integration, offline decoder and checks are in Tools/.
- Local/remote setup: docs/SETUP.md. Web usage: Tools/nw_capture/web/README.md.
- OAuth and recovery: Tools/nw_capture/web/YOUTUBE.md.
- A full capture/unlisted-live/Stop/archive cycle was verified earlier on the old
  deployment. This does not mean the new directory was deployed or live-tested.
- The current archive contains a YouTube link, not the video file. Local backup
  video stays on the gaming host. Do not restore video embedding in the ZIP.
- Our local capture data is copied and gitignored. A private Python environment
  and checksum-verified, gitignored Windows Frida server 17.9.10 are installed.
- External references: docs/REFERENCES.md, including Aeternum-World, First Light,
  NWDB and nw-buddy. Preserve the AGPL license and upstream attribution.

## Completed background work and a correction

Workflow 3b9ee3ed-e143-4adc-9750-c538c5b28fd4 finished and its source/reports were
imported. No pending workflow import remains.

Import review found that its Carrier parser read an explicit two-byte reliable
sequence without advancing the cursor. We added the missing `i += 2` in
Tools/nw_capture/decode_dtls_ledger.py and a regression that failed before the fix
and passed afterward. Both saved captures were rerun. **The workflow's original
numeric results are superseded by the reports in this repository.** Do not
resynchronize the old decoder over this corrected one.

Current evidence:

- docs/Network/offline-position-proof.md
- docs/Network/hive-capture-position-proof.md
- private/hive-workflow-import.json (source and corrected-file hashes)
- private/hive-post-import-diagnostic.json (aggregate external comparison)
- Tools/nw_capture/captures/offline-position-scratch/new-workspace-diagnostic.json

## What the other capture taught us

The external Hive capture has four separate connection windows. Each channel-1
sequence starts at zero and is continuous within that window; combining windows
had produced false order errors. Chunk reassembly completes without observed
countdown/sequence errors in those streams.

It provides cleaner sequence evidence than our Test teleport capture, which has
11 sequence gaps/order breaks. However, cleaner sequences did not validate our
application framing hypothesis: most application bytes remain unresolved.
We must not assume that simply collecting more traffic will resolve the schema.

Corrected results:

| Observation | Hive | Our Test teleport |
|---|---:|---:|
| Ledger records | 40,254 | 6,354 |
| Parsed Carrier messages | 78,799 | 11,923 |
| Reassembled IN ch1 pieces | 25,768 | 4,120 |
| Varint-length application candidates | 258 | 421 |
| Unresolved application bytes | 3,366,723 | 1,127,682 |

These are bounded parsing candidates, not verified gameplay messages. Hive's two
marker-like candidates fail exact consumption (`payload_leftover`). Our capture's
881 marker-like matches fail `has_sequence_invalid`. No exact StateBundle or inner
member boundary is verified. Positions, player identity, rotation, equipment
changes and local-player ownership remain undecoded. Type-13/coordinate parsing
is not attempted, not a measured absence of positions in the traffic.

## Next technical step

Resolve actual application stream framing and the type-8 body using the matching
client's deserializer. Account for unresolved Carrier tails and sequence gaps.
Treat First Light's notes and the static catalog as references, not an authoritative
schema for this build. Do not scan arbitrary floats and present them as a trail.
Only add the live map after coordinates and local-player attribution are validated
against recorded movement/teleport evidence.

## Reproduce our offline check

From the new repository root:

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/test_decode_saved_position.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_saved_position.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin \
  --out-json Tools/nw_capture/captures/offline-position-scratch/new-workspace-diagnostic.json
```

After import/correction, the offline regression, both ledger reruns, 15 capture
Python tests, 8 web Python tests, both Node lifecycle modes, OAuth checks and Python
compilation passed. README.md contains the runnable checks. Live gameplay decoding,
a coordinate plot and a new deployment were not verified.

## What was intentionally not moved

The other user's Hive RAR/ledger, Catalog/game dumps, First Light checkout,
upstream raw logs and host OAuth/SSH/Steam credentials are not bundled here.
The Hive ledger remains in the old workspace's
Tools/nw_capture/captures/offline-hive-scratch/ directory and was read there only.
Own captures and private aggregate results are local, gitignored and not backed up
by Git. Do not delete the original workspace or remote deployment during handoff.

The existing game, streaming host, tunnel and capture service were not restarted
or relocated. Old host paths in historical setup notes still describe that live
deployment. Switching deployment is a separate operator-controlled step after
capture stops and owned-worker cleanup is verified.

This is a local Git repository on main, with no remote or initial commit as of
this handoff. Files are saved on disk, not pushed or externally backed up. Check
Git status and review the source-only file set before committing or publishing.
