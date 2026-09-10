# Working rules

- Start by reading docs/NEXT_SESSION.md; it preserves the conversation context and next steps.

- Use English for code, comments, documentation and UI. Preserve historical evidence verbatim.
- This is the continuation workspace. Do not edit the old Aeternum-World checkout as part of new work.
- Read docs/HANDOFF.md before continuing the offline decoder: the completed workflow import includes a cursor fix absent from the old checkout.
- Do not interrupt or relocate an existing background run during the workspace handoff.
- Never operate game input, capture Start/Stop, live streams or cloud resources without task authorization.
- Keep changes small; reuse existing parsers and leave a runnable check for new logic.
- Do not claim coordinates, self-player identity or a trail from marker matches or arbitrary float scans.
- Capture files, raw payloads, keylogs, credentials, videos and machine configuration stay private and gitignored.
- Never commit external captures or vendored game/reference dumps. Cite Aeternum-World, First Light and NWDB through docs/REFERENCES.md.
- Preserve AGPL licensing and attribution for upstream-derived tooling.
- Keep setup instructions reproducible for local and remote hosts; separate historical verification from current runtime claims.
- Check Git status and review the explicit source file set before committing. Do not publish this repository or raw data without authorization.
