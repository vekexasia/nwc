# External references and attribution

## Aeternum-World

- Repository: https://github.com/Coldzer0/Aeternum-World
- Protocol reference: https://github.com/Coldzer0/Aeternum-World/blob/main/docs/Network/packet_system.md
- Class catalog: https://github.com/Coldzer0/Aeternum-World/tree/main/Catalog

Our capture stack originated in this repository. The retained/adapted files include
`_common.js`, `_dtls_ledger.js`, `_runner.py`, `nw_capture.py`, `nw_https_tap.js`,
`decode_dtls_ledger.py`, `extract_https_pairs.py`, requirements and capture guidance.
The capture checklist credits Mattsin in its original attribution, retained here.
Subsequent work added/changed Proton attachment, lifecycle validation, the shared
web service, video/YouTube handling, local launch helpers and offline diagnostics.
Preserve existing notices and the upstream AGPL-3.0 license. Our separation into
another Git repository does not remove upstream authorship or license obligations.

The Catalog, original protocol-reference document, upstream raw logs and game dumps
are not vendored. Research notes may cite their original file names and line numbers;
those citations refer to the source workspace/repository, not missing local dependencies.
A migration manifest with the upstream commit and source snapshot hashes is kept
locally in gitignored `private/migration-manifest.json`.

## First Light

https://github.com/nw-private-server/first-light

Historical New World private-server/protocol research, including Carrier framing,
replication analysis and capture tooling. Its README marks it defunct and refers
active development to OpenWorld Discord. No First Light source or datasets are
copied here. The inspected snapshot had no explicit root license file; consult
the authors before incorporating code rather than treating visibility as a license.

## NWDB

https://nwdb.info/

Independent New World database. No official public general API, source repository
or reusable map-data license was verified. Its documented integration is
https://nwdb.info/tooltips; terms: https://nwdb.info/terms-and-conditions.
Do not scrape/rehost its data or tiles without the required permission. It does not
supply our live player positions. No NWDB assets are bundled.

## ratbuddy / ow.ratbuddy.com

- Dashboard: https://ow.ratbuddy.com/, indexing `/completeness/`, `/spectrum/`, `/slayer/` and
  `/ai-trees/`. The site titles itself "New World Private-Server". Observed 2026-09-10.

`/spectrum/` publishes retail-vs-current-build replication diffs from an internal tool
(`traffic-spectrum-diff r1`), frame-binned over channel-1 server-to-client StateBundle traffic.
Its metric key names `alc_rows`, `action_rows`, `sequence_only_rows` and `abs_rows` ("ALC rows
with `world_pos.abs`"), which independently corroborates our ALC static analysis. `/completeness/`
is a per-action evidence ledger over a 235-capture corpus; it holds no position or transform entry
and its movement tab contains only local input and unscanned swimming items.

No license, no terms of use and no `robots.txt`: `/robots.txt`, `/about/` and `/terms/` all return
the root page. Treat the site as all rights reserved. Both pages state that their databases,
ledgers and capture files are internal and that only reviewed source labels and aggregate metrics
are published. Do not copy the published tables, nor extract the payload embedded in the page
HTML, into this repository: the compilation is a database under art. 102-bis LDA (dir. 96/9/CE
art. 7) and no permission to reuse a substantial part of it exists. Cite derived facts instead, as
done here.

`github.com/ratbuddy/nw-sim`, referenced by the Discord decode notes, no longer exists (HTTP 404
on 2026-09-10); the public `ratbuddy` account lists no New World server-simulation repository.

## Other useful upstreams

- nw-buddy: https://github.com/giniedp/nw-buddy and https://www.nw-buddy.de/
- Frida: https://github.com/frida/frida/releases
- Sunshine: https://github.com/LizardByte/Sunshine
- Moonlight: https://moonlight-stream.org/
- Google OAuth: https://developers.google.com/identity/protocols/oauth2/native-app
- YouTube broadcast API: https://developers.google.com/youtube/v3/live/docs/liveBroadcasts

These are references, not claims of affiliation, compatibility or permission to
redistribute their code/assets. Record provenance and verify the applicable license
before introducing third-party material.
