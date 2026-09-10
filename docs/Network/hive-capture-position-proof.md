# Shared Hive capture position proof

## Result after import correction

No verified coordinates, player identity or trail were decoded. Type-13/member
and coordinate decoding remain explicitly not attempted: neither marker-like
candidate consumes an exact StateBundle under the tested hypothesis.

This report supersedes workflow `3b9ee3ed-e143-4adc-9750-c538c5b28fd4`'s original
counts. Import review found a missing two-byte cursor advance after explicit
reliable-sequence reads in `decode_dtls_ledger.py`. The new repository fixes it,
with a regression that failed before the fix and passed afterward. Both saved
ledgers were rerun with the corrected code. The old workspace was not modified.

## Input and isolation

- External archive: `Hive great sword and flail with shield and without shield.rar`.
- Archive SHA-256: `defe54d51ebb2a4a85e715d2c6ac8feb831c85f1b7e51da039d012f1c5511852`.
- Ledger SHA-256: `00a5b7ce40f24dd87f8f8eace029d17dab1ef6cab6566f60ac4a33b0b76f7c5a`.
- The already extracted ledger in the old workspace was opened read-only.
- Neither this other user's RAR nor its ledger was copied into this repository.
- Only aggregate results are retained. No raw payloads or credentials were
  printed/uploaded, and no live capture, game input or cloud operation occurred.

To repeat locally, supply the external ledger path explicitly:

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/test_decode_saved_position.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_saved_position.py \
  /PATH/OUTSIDE/THIS/REPO/ledger.bin \
  --out-json private/hive-post-import-diagnostic.json
```

The `private/` output is gitignored. The migration rerun read
`~/git/personale/Aeternum-World/Tools/nw_capture/captures/offline-hive-scratch/ledger.bin`.

## Verified corrected aggregates

| Observation | Hive | Our Test teleport |
|---|---:|---:|
| Complete ledger bytes | 7,478,558 | 1,501,859 |
| Accepted outer datagrams | 40,254 | 6,354 |
| Carrier messages | 78,799 | 11,923 |
| Datagrams fully consumed through Carrier | 3,572 | 1,050 |
| Datagrams with Carrier rejection/trailer | 36,682 | 5,304 |
| Retained trailer bytes | 99,706 | 21,943 |
| IN channel-1 messages | 26,886 | 4,725 |
| Reassembled pieces | 25,768 | 4,120 |
| Length-delimited application candidates | 258 | 421 |
| Unresolved application bytes | 3,366,723 | 1,127,682 |
| Marker-like occurrences | 2 | 881 |

Hive has four anonymous connection windows. Their channel-1 counts are
8,119 / 8,132 / 8,181 / 2,454; reassembled counts are
7,902 / 7,853 / 7,789 / 2,224. Each sequence stream starts at zero and has no
observed gaps/order breaks. The old global order breaks were artifacts of joining
separate connections. This does not establish complete application coverage.

The analyzer applies inbound varint length framing across reassembled pieces per
connection. On Hive it stops on two out-of-range lengths, one overlong length and
one truncated message. The resulting 258 candidates are bounded cuts under this
hypothesis, not independently verified semantic messages.

The two `00 01 08 01` matches occur at offsets 1,774 and 47,100. Both reject at
`payload_leftover`, leaving 8,847 and 42,962 bytes. Neither supplies an exact
StateBundle/member boundary. Our Test teleport has 11 sequence gaps/order breaks;
its 421 candidates stop at a truncated message and all 881 marker-like matches
reject at `has_sequence_invalid`. See the [local proof](offline-position-proof.md).

## Reference limits

First Light documents a type-8 anchor and an opaque subtype-dependent tail, not
a complete StateBundle member schema. Aeternum-World's static catalog identifies
type index 13 as `MB::PositionInTheWorldReplicatedState`, but that alone establishes
neither the capture's runtime registry nor local-player ownership. See
[REFERENCES.md](../REFERENCES.md); these external sources are not vendored.

The workflow inspected `/tmp/first-light-research` read-only. Its snapshot had no
Git metadata; the recorded aggregate file-list SHA-256 was
`1bae70e6c4813498ff8fbaf596c59db3609a7f9ad1d876e73a7e93c9ad340e25`.
The workflow used `find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum`.

The result does not prove positions are absent from the capture. It shows that the
current bounded parsing hypotheses do not expose validated coordinates without
guessing boundaries or ownership. No coordinate plot was generated.
