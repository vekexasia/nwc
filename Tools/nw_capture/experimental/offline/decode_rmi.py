"""List the typed messages a join log recorded as ``rmi_samples`` (everything the type reference reader
saw that is not a replicated-state chunk), named through the community catalog.

Each item is ``[ts, typeIndex, bytes_after_hex]``: the bytes start right after the type reference,
i.e. at the message body. Client-facet RMIs open with a 16-byte target uuid (nw_rmi_probe.js run,
2026-09-11 20:04: TimeComponentClientFacet_SyncDayPhase = uuid + 00000002).

    decode_rmi.py --log Tools/nw_capture/logs/<run>_live.log [--type N] [--limit 5]
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from list_replicated_states import TRIAGE, ENTRY_RE  # noqa: E402


def catalog_names(path=TRIAGE) -> dict:
    """typeIndex -> (short name, message kind) for every catalog entry, states included."""
    names = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return names
    for raw in ENTRY_RE.findall(text):
        entry = json.loads(raw)
        names[entry["type_idx"]] = (entry["name"].split("::")[-1], entry.get("message_kind", ""))
    return names


def _string(payload: bytes, index: int):
    """A length-prefixed ASCII/UTF-8 string (u8 length), as the chat message uses."""
    if index >= len(payload):
        return None, index
    length = payload[index]
    end = index + 1 + length
    if end > len(payload):
        return None, index
    return payload[index + 1:end].decode("utf-8", "replace"), end


def parse_chat(payload: bytes):
    """ChatComponentClientFacet_ReceiveChatMessage (4118): 16-byte target uuid, then the sender's
    character uuid as a 36-char string, the sender name, six bytes (channel and flags), the text, twelve
    zero bytes, 01, the Steam id string, 01 03. Read on the player's own 'ciao' (live 20:13)."""
    if len(payload) < 20:
        return None
    index = 16
    sender_id, index = _string(payload, index)
    name, index = _string(payload, index)
    if name is None or index + 6 > len(payload):
        return None
    channel = payload[index]
    text, index = _string(payload, index + 6)
    if text is None:
        return None
    return {"name": name, "text": text, "channel": channel, "sender_id": sender_id}


def parse_chat_batch(payload: bytes):
    """ChatComponentClientFacet_ReceiveBatchedChatMessages (293): uuid, u8 count, then the messages."""
    if len(payload) < 17:
        return []
    count = payload[16]
    out, index = [], 17
    for _ in range(count):
        message = parse_chat(payload[:16] + payload[index:])
        if message is None:
            break
        out.append(message)
        # advance: 36-char id (1+36), name (1+n), 6, text (1+m), 12 zeros, 01, steam id (1+k), 01 03
        _sid, index2 = _string(payload, index)
        _name, index2 = _string(payload, index2)
        _text, index2 = _string(payload, index2 + 6)
        index2 += 13
        _steam, index2 = _string(payload, index2)
        index = index2 + 2
    return out


def samples(lines):
    for line in lines:
        if '"rmi_samples"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        for item in entry.get("items", []):
            yield item


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--type", type=int, help="dump the bodies of one typeIndex")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    names = catalog_names()
    counts, bodies = Counter(), defaultdict(list)
    for _ts, type_index, after in samples(args.log.read_text(errors="ignore").splitlines()):
        counts[type_index] += 1
        if len(bodies[type_index]) < args.limit and after not in bodies[type_index]:
            bodies[type_index].append(after)
    if args.type is not None:
        for body in bodies.get(args.type, []):
            print(body)
        return 0
    for type_index, count in counts.most_common():
        name, kind = names.get(type_index, ("?", "?"))
        print(f"{type_index:6} {count:7}  {kind:16} {name[:60]:60} {bodies[type_index][0][:48] if bodies[type_index] else ''}")
    return 0


def check():
    body = bytes.fromhex("515ac85acc363edc31df13d046e908f82433643331383031302d623431362d346230622d386266372d366565323532"
                         "313836643664085065746157617474020000000000046369616f00000000000000000000011137363536313139393532"
                         "3233373438313801 03".replace(" ", ""))
    message = parse_chat(body)
    assert message and message["name"] == "PetaWatt" and message["text"] == "ciao" and message["channel"] == 2, message
    batch = bytes.fromhex("515ac85acc363edc31df13d046e908f8012431326439666163362d663738312d346332612d613061332d363466323532"
                          "353033313066094379646572582e4e5402000000000e342b4d59524b2052554e202f2f2f2020535441525420202f2f2f"
                          "2028506f7274616c205570292031382f323020342e506f7274616c0000000000000000000001113736353631313939303530"
                          "3731373734330103")
    messages = parse_chat_batch(batch)
    assert len(messages) == 1 and messages[0]["name"] == "CyderX.NT" and messages[0]["text"].startswith("+MYRK RUN"), messages
    print("decode_rmi check ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    else:
        raise SystemExit(main())
