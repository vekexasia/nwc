# NWDB and First Light research

Verified against live pages on 2026-09-10. NWDB here means **New World Database**, not an Amazon Games service.

## NWDB: primary website

- **Website:** [nwdb.info](https://nwdb.info/)
- The homepage identifies itself as **New World Database** and describes coverage of items, quests, crafting recipes, perks, abilities, population numbers, and more. Its canonical URL is `https://nwdb.info/` and its title is `Home - New World Database`. [Homepage](https://nwdb.info/)
- The site exposes the database directly through pages such as [Items](https://nwdb.info/db/items/page/1), [Quests](https://nwdb.info/db/quests/page/1), [Perks](https://nwdb.info/db/perks/page/1), and [Server Status](https://nwdb.info/server-status).
- There is no verified public About page: `https://nwdb.info/about` returned 404 when checked. The site instead identifies itself in the footer as “NWDB aims to bring you the most comprehensive database for New World.” [Terms and Conditions](https://nwdb.info/terms-and-conditions)
- The footer links to [Terms and Conditions](https://nwdb.info/terms-and-conditions), [Privacy Policy](https://nwdb.info/privacy-policy), [Tooltip Syndication](https://nwdb.info/tooltips), the [NWDB Discord](https://discord.gg/RtM6q3ksuD), and [@nwdb_info on Twitter/X](https://twitter.com/nwdb_info). It does **not** link to GitHub.

## Source, data, and integrations

- No public NWDB source repository or NWDB data dump was verified. The public GitHub account named [NWDB](https://github.com/NWDB) currently has zero public repositories, and the GitHub repository search for `nwdb.info` returned only the unrelated third-party tool listed below. [GitHub search](https://github.com/search?q=nwdb.info&type=repositories)
- NWDB's terms explicitly prohibit scraping, unusual/script access, and reproducing its content elsewhere. Do not infer an official API or source-data license from the existence of database pages. [Terms and Conditions](https://nwdb.info/terms-and-conditions)
- NWDB does publish one documented developer integration: [Tooltip Syndication](https://nwdb.info/tooltips), which instructs developers to load [`https://nwdb.info/embed.js`](https://nwdb.info/embed.js) so links to NWDB item/perk/etc. pages receive pop-up tooltips. The page grants use only through the original script/instructions, gives no accuracy/availability guarantee, and is not a general data API.
- **Third-party, not official NWDB source:** [StefanRandomnumbers/NWDB_PerkChances](https://github.com/StefanRandomnumbers/NWDB_PerkChances) describes itself as a New World tool that accepts an `nwdb.info` crafted-gear link and calculates perk-roll chances. It is an independent consumer of NWDB links, not an NWDB repository or endorsement.

## First Light GitHub repository

- **Repository:** [nw-private-server/first-light](https://github.com/nw-private-server/first-light)
- **Organization:** [nw-private-server](https://github.com/nw-private-server). GitHub lists this organization as public and currently lists one public repository, `first-light`. [Organization API record](https://api.github.com/orgs/nw-private-server)
- The repository README describes a community New World private-server emulator/reverse-engineering effort. It says “First Light” refers to the New World territory that was later removed from the game. [README](https://github.com/nw-private-server/first-light/blob/main/README.md)
- The current README marks the repository **defunct**, says it is retained as a historical reference, and directs active development to the OpenWorld Discord. Therefore it should not be treated as an active supported source repository. [Raw README](https://raw.githubusercontent.com/nw-private-server/first-light/main/README.md)
- The repository contains public analysis, capture, server, and tooling material, but it is separate from NWDB. No primary evidence was found on the NWDB site/footer or in the First Light README that links the two projects. Their verified connection is only that both concern the New World game; “First Light” is also the name of the in-game territory referenced by the emulator project.

## Bottom line

Use [https://nwdb.info/](https://nwdb.info/) as the exact NWDB website. Treat `nwdb.info/embed.js` as the only explicitly documented developer integration found, and do not call third-party GitHub tools official. Use [nw-private-server/first-light](https://github.com/nw-private-server/first-light) for the requested First Light repository, with the important status caveat that its own README now says it is defunct.
