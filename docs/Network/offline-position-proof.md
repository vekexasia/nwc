# Offline saved capture position proof

## Current result

No verified position, local-player identity or trail has been decoded. The saved
Test teleport ledger is complete, but application framing and the StateBundle
hypothesis remain unresolved. Member/type-13/coordinate decoding is explicitly
**not attempted**, not a measured count of zero positions in the capture.

This report supersedes the initial experiment and the pre-import workflow counts.
During import of workflow `3b9ee3ed-e143-4adc-9750-c538c5b28fd4`, review found that
`_parse_carrier_messages` read an explicit two-byte reliable-sequence field without
advancing the cursor. The new workspace fixes that missing `i += 2`. A synthetic
regression failed before the fix and passed afterward, covering payload boundaries,
explicit/derived reliable sequence IDs and ordinary sequence wraparound.

## Input and isolation

- Original archive: `~/Downloads/Test-teleport.zip`, unchanged.
- Archive SHA-256: `7e0c5defe627fe40c57713d18260bf63b8d2ee095ae39735e13df11194a251dc`.
- Session: `475be10d-d168-4542-aefa-72f6524e8906`.
- Member: `captures/proton_20260910_095553/dtls/ledger.bin`.
- Local fixture: `Tools/nw_capture/captures/offline-position-scratch/ledger.bin`.
- Raw data remains gitignored and private. No live game, web controls or cloud
  resources were operated. No raw payloads or credentials were printed/uploaded.

## Reproduction in this workspace

Install the environment described in [SETUP.md](../SETUP.md), then:

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/test_decode_saved_position.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_saved_position.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin \
  --out-json Tools/nw_capture/captures/offline-position-scratch/new-workspace-diagnostic.json
```

## Verified post-fix aggregates

| Observation | Result |
|---|---:|
| Ledger bytes consumed | 1,501,859 / 1,501,859 |
| Datagrams accepted at outer layer | 6,354 / 6,354 |
| Carrier messages parsed | 11,923 |
| Datagrams fully consumed through Carrier | 1,050 |
| Datagrams with Carrier rejection/trailer | 5,304 |
| Retained trailer bytes | 21,943 |
| IN channel-1 messages | 4,725 |
| Reassembled pieces | 4,120 |
| Completed chunk groups | 77 |
| Channel-1 gaps/order breaks | 11 / 11 |
| Length-delimited application candidates | 421 |
| Unresolved application bytes | 1,127,682 |
| Marker-like occurrences | 881 |

The inbound varint-length hypothesis produces 421 bounded message candidates,
then stops on a truncated message. This is not verified semantic application
coverage. Of the marker-like occurrences, 395 are at candidate offset zero;
all 881 StateBundle attempts fail `has_sequence_invalid`. No inner member
boundary or coordinate is accepted. Pattern counts are not validated type IDs.

Carrier reassembly checks do not establish a lossless application stream. Retained
trailers now include the complete rejected frame/header, not merely bytes after
a partially consumed header; that changes trailer-byte totals from the first run.

## Sources and next boundary

The experiment reuses our `Tools/nw_capture/decode_dtls_ledger.py`. It compares
bounded hypotheses from Aeternum-World's packet notes/catalog and First Light's
Carrier/type-8 analysis; see [REFERENCES.md](../REFERENCES.md). External reference
code/dumps are not bundled. A catalog entry naming
`MB::PositionInTheWorldReplicatedState` does not establish its on-wire boundaries,
runtime index mapping or association with the local player.

Next: resolve channel stream framing and the type-8 body against the matching
client's deserializer. Do not generate a map from arbitrary floats or interpret
unimplemented coordinate decoding as proof that the capture lacks positions.

Verification: offline regression and both saved-ledger reruns passed; 15 capture
and 8 web Python tests plus both Node lifecycle modes and OAuth checks passed.
No gameplay replay or coordinate plot was produced because no coordinates were validated.
