# Ledger framing gaps

## Result

The reported zero-frame result is reproducible only for `proton_20260911_105731-walktest` when the full `decode_in_bodies.py` run is used. The jump and dodge ledgers already contain frames under the current decoder. The control ledger `proton_20260910_174014-alcact` still has 7,220 exact frames. No source decoder change is justified by these measurements.

`exact closures` means marker pairs accepted by the existing `iter_frames`: the big-endian length at marker offset `+12`, followed by a 1..5-byte prefix-varint before the next marker.

| ledger | ledger bytes | `ssl_ptr` set | IN / OUT ledger records | IN ch1 stream bytes | marker occurrences | exact closures | ALC records |
|---|---:|---|---:|---:|---:|---:|---:|
| `proton_20260911_105731-walktest` | 2,511,512 | `0x4815d1b0` | 8,861 / 2,874 | 1,701,518 | 7,237 | 0 | 0 |
| `proton_20260911_081033-jump` | 133,776 | `0x477e0a20` | 931 / 333 | 46,081 | 831 | 828 | 1,644 |
| `proton_20260911_091552-dodge` | 517,886 | `0x477e0a20` | 1,955 / 673 | 333,600 | 1,784 | 1,282 | 8,882 |

The ALC counts are from `decode_alc_state.py --limit 0`. The frame counts are full runs of `decode_in_bodies.py` without a frame limit. Thus the two latter ledgers do not produce zero frames in this checkout; their exact frame counts are lower than their marker counts because some marker pairs do not close under the grammar.

## Measurements

The following are decoded Carrier-message counts. The channel columns are `ch0 / ch1 / ch3 / no channel` (`no channel` means that the Carrier data-channel flag was absent).

| ledger | IN Carrier messages | OUT Carrier messages | IN ch1 rows / reassembled pieces | ch1 sequence (`first..last`, gaps/order breaks) |
|---|---:|---:|---:|---|
| walktest | 347 / 7,678 / 7,876 / 457 | 312 / 1,512 / 2,864 / 370 | 7,678 / 7,236 | `0..7684`, 7 / 7 |
| jump | 34 / 837 / 923 / 0 | 28 / 139 / 332 / 41 | 837 / 831 | `57715..58551`, 0 / 0 |
| dodge | 57 / 1,836 / 1,851 / 1 | 49 / 443 / 673 / 33 | 1,836 / 1,784 | `58439..60275`, 1 / 1 |

Each ledger has one `ssl_ptr` and one contiguous pointer run. Hypothesis (a), mixing multiple SSL connections in `channel_stream`, is therefore not the cause in these three files. The Carrier decoder accepted the incoming datagrams without a Carrier or LZ4 error. Incoming datagram mode counts (`0x81` compressed / `0x80` uncompressed) were walktest `7,396 / 1,465`, jump `9 / 922`, and dodge `1,838 / 117`.

The first 32 bytes of each reassembled IN channel-1 stream are:

```text
walktest dff00703a470c963dac35f1ab2a110d0a295255901080101010101010000c1
jump     2f00010801c35f06010401010000210101100b01e70001404da0e8103648a7ab
 dodge   870200010801c55e14010401010000790101100b03e7000140c948fb309a32e5
```

For jump, `2f` is a one-byte prefix-varint for 47 bytes and the marker starts at stream offset 1. For dodge, `87 02` is a two-byte prefix-varint for 135 bytes and the marker starts at offset 2. These are consistent with the existing frame stream: a length prefix before the next marker is the trailer seen by `iter_frames`.

Walktest is different. Its first three bytes, `df f0 07`, decode as a prefix-varint length of 1,966,335 bytes. Only 1,701,515 bytes follow that prefix in the captured channel stream, a deficit of 264,820 bytes. The first marker-like occurrence is at offset 65,061, and every one of the 7,237 occurrences is inside the available bytes of this incomplete length-delimited message. The bytes after those occurrences are not the established four-byte frame constant: `04 01 01 00` occurs zero times at marker offset `+8`, while `01 01 01 00` occurs only eight times. Those occurrences cannot establish frame boundaries.

Sequence gaps also do not explain the result: walktest has seven channel-1 sequence gaps/order breaks, but jump has none and dodge has one while both frame successfully. The apparent `01 01 01 01` data after many walktest marker occurrences is inside the large message body, not evidence for a one-byte-counter frame variant.

## Cause and decision

**Verified:** the three ledgers do not mix multiple `ssl_ptr` streams. Carrier reassembly and both LZ4 modes complete without parser errors.

**Inferred from the length prefix and truncation:** walktest starts with a large application message whose body is incomplete in this ledger. Its 4-byte marker occurrences are embedded body data, so the known marker/u32/constant/u16/trailer grammar cannot frame it. This is the same class of limitation already noted for the larger session in `alc-protocol-reference.md` section 1: a marker occurrence is not a boundary unless the complete grammar closes around it.

No change was made to `decode_in_bodies.py` or `test_decode_in_bodies.py`. Generalizing `iter_frames` to accept the walktest occurrences would invent boundaries and could expose partial records as valid ALC data. The jump and dodge results remain the existing decoder behavior.

## Reproduction

From the repository root, using only saved ledgers:

```sh
for name in \
  proton_20260911_105731-walktest \
  proton_20260911_081033-jump \
  proton_20260911_091552-dodge
 do
   ledger="Tools/nw_capture/captures/$name/dtls/ledger.bin"
   .venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_in_bodies.py "$ledger"
   .venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_alc_state.py \
     --ledger "$ledger" --limit 0
 done
```

The Carrier direction/channel and mode measurements can be reproduced with:

```sh
.venv-capture/bin/python Tools/nw_capture/decode_dtls_ledger.py \
  Tools/nw_capture/captures/proton_20260911_105731-walktest/dtls/ledger.bin \
  --summary-only
```

The same command accepts either of the other two ledger paths. The per-pointer and marker measurements above are a read-only scan using the existing `iter_ledger`, `decode_record`, `reassemble_channel_messages`, `find_all`, and `iter_frames` functions; no capture process or game input is required.
