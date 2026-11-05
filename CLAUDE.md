# openuap — notes for Claude

Consolidated UFO/UAP event database: SQLite + FTS5, loaders per source, read-only query layer,
MCP server and a Claude `ask` agent. Read HANDOFF.md first for current state and open items.

- Install: `pip install -e .`  Build: `openuap fetch && openuap build` (~20 s). Tests: `python3 -m pytest -q tests`.
- The database (`data/openuap.sqlite`) and `data/raw/` are git-ignored; rebuild rather than commit them.
- Every new test must be proved red (plant a fault, watch it fail, revert) and the evidence noted in HANDOFF.md.
- Never push to main; work on a branch. Commit with explicit paths (`git commit -o <paths>`).
- Licences differ per source; see the `sources` table and README before redistributing data.
- Keep HANDOFF.md current at each milestone.
