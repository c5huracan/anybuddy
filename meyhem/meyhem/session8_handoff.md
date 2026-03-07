# Meyhem — Session 8

Continue developing and promoting Meyhem — an agent-native search engine with outcome-driven ranking.

---
**Handoff from previous session (Session 7):**

- **Problem:** Traffic and adoption plateaued. One power user (openclaw-agent), zero installs on meyhem-search despite 107 views. ClawHub security scan flagged both skills as "Suspicious" — the #1 conversion killer.

- **Progress so far:**

  **ClawHub security fix (major):**
  - Root cause identified: `search.py` bundled with meyhem-search imported nonexistent `meyhem` package, used wrong agent-id (`pi-agent` instead of `openclaw-agent`), triggered 3 of 4 security flags (undocumented Python dependency, agent-id mismatch, missing install mechanism)
  - Fix: backed up search.py to `~/anybuddy/meyhem/meyhem/backups/search.py.bak`, deleted from skill package, added `pip: meyhem` to SKILL.md requires, strengthened Data Transparency section
  - Published meyhem-search 0.1.7, meyhem-researcher 0.1.8 — awaiting security rescan to clear "Suspicious" badge
  - ⚠️ search.py still exists in GitHub public repo (c5huracan/meyhem, meyhem-search/ directory) — needs to be deleted from GitHub in next session

  **SKILL.md rewrites (both skills):**
  - Replaced wall-of-curl documentation with value-prop-first layout
  - Added "Why Meyhem?" bullet points, Quick Start (Python + REST), MCP section, explicit Data Transparency section
  - Removed inflated social proof numbers (700+ searches, 490+ domains included seeder data). Honest stats: ~364 organic searches, ~95 truly external
  - Keywords optimized for ClawHub search: "web search", "multi-engine", "outcome-ranked"

  **GitHub public repo (c5huracan/meyhem):**
  - README.md updated: value prop, honest stats, OpenClaw listing added
  - Both SKILL.md files synced to public repo
  - ⚠️ meyhem-search/search.py still on GitHub — delete it to match ClawHub package

  **meyhem PyPI package:**
  - v0.1.1 on PyPI, v0.1.0 installed locally on solveit instance
  - Both SKILL.md files now declare `pip: meyhem` as a dependency
  - ⚠️ Not yet verified that `pip install meyhem` + basic usage actually works end-to-end — do this before promoting further

  **Google Search Console:**
  - Verified via HTML meta tag (already in deployed landing.html — do not remove)
  - Sitemap submitted (https://api.rhdxm.com/sitemap.xml)
  - Indexing requested for / and /docs
  - Google had already crawled site (via Reddit r/ClaudeAI backlink) but chose not to index — "crawled, currently not indexed"
  - Referring page: reddit.com/r/ClaudeAI (so that post wasn't totally wasted)

  **VoltAgent awesome-openclaw-skills PR #207:**
  - Still open, 0 comments, mergeable. Created after a batch rejection sweep (5 PRs rejected, 5 merged on Mar 5 ~11:21 UTC)
  - Rejected PRs got zero feedback — silent closes
  - Merged PRs were focused, specific tools. Unclear if ours fits the pattern
  - Deprioritized — awesome lists are low ROI compared to ClawHub

  **awesome-mcp-servers PR #2527 (punkpeye, 82k stars):**
  - Blocked on `missing-glama` label — requires Glama listing
  - Glama submission explored: meyhem is a hosted service, not a standalone MCP server
  - Glama "connectors" route is better fit than "servers" but unclear if it satisfies the requirement
  - Deprioritized — high effort, uncertain payoff

  **Strategy pivot:**
  - Awesome lists deprioritized (time sink with diminishing returns)
  - ClawHub is the channel that works — both organic users came through OpenClaw agent discovery
  - Chinese seeder batches deprioritized — power user generates real organic signal (276+ searches), better than seeded data
  - JP/KR seeder batches dropped — zero evidence of demand in query data, pure speculation
  - Focus: ClawHub discoverability, Discord community engagement

  **New organic activity during session:**
  - openclaw-agent: still active, 276 searches (was 269). Researching A-shares, smart home, OpenClaw ecosystem
  - researcher-agent: NEW agent, 3 searches ("AI agent skills ClawHub 2026") — brief burst, may return
  - Landing page: +27 views during session (296->323), possibly from ClawHub "recently updated" bump
  - Docs: +3 views (63->66)

  **OpenClaw Discord:**
  - Invite links: discord.com/invite/openclaw (14k members), discord.gg/clawd
  - OpenClaw uses Pi SDK as agent loop engine; ClawHub agents auto-discover skills — this is likely how power user found us
  - Intro post drafted but ON HOLD until ClawHub security scan clears — don't want first impression with "Suspicious" badge
  - Draft post theme: "Meyhem: Agent-native search that gets better as agents use it" — mention ClawHub skills, MCP endpoint, REST, no API key, ask for feedback

  **Stats at close:**
  - 713 searches, 39 agents, 1154 selections, 1675 outcomes
  - 323 landing views, 66 docs views
  - openclaw-agent: 276 searches (daily Chinese power user, topics: A-share investing, smart home, AI/LLM tools, prompt engineering, marketing, education)
  - researcher-agent: 3 searches (new, unconfirmed)
  - alex-scrumball: 13 searches (returning external user, inactive this session)
  - meyhem-search: 0.1.7 on ClawHub, meyhem-researcher: 0.1.8 on ClawHub

- **Next steps (priority order):**
  1. Check ClawHub security rescan — this is the #1 blocker. If still "Suspicious", investigate further or contact ClawHub support
  2. Delete search.py from GitHub public repo (meyhem-search/ directory)
  3. Verify meyhem PyPI package works: `pip install meyhem --upgrade` then test `Meyhem('test').search('hello')`
  4. Post Discord intro once scan clears — draft ready
  5. Monitor researcher-agent — if they return with varied queries, that's user #2
  6. Google indexing — check Search Console in a few days for coverage
  7. Monitor funnel: ClawHub views -> installs conversion after security clears
  8. Consider splitting main.py into modules (~500+ lines)
  9. HN shadowban — still unresolved, check hn@ycombinator.com reply
  10. Cursor forum — still pending approval

- **Notes:**
  - Deploy: `pc.deploy(path=Path.home()/'anybuddy/meyhem/deploy')`
  - Stats: `httpx.get(PROD_URL+'/stats', headers=_auth).json()`
  - Corpus: `httpx.get(PROD_URL+'/stats/corpus', headers=_auth).json()`
  - Queries by agent: `httpx.get(PROD_URL+'/stats/queries', params=dict(agent_id='...'), headers=_auth).json()`
  - ClawHub: `export PATH="$HOME/.bun/bin:$PATH" && clawhub inspect/publish/search`
  - GitHub: `api = GhApi()`, public repo: c5huracan/meyhem, private: c5huracan/meyhem-private
  - Backups: `~/anybuddy/meyhem/meyhem/backups/search.py.bak`
  - Organic vs total: ~364 organic searches out of 713. Seeder/test: 193, internal: 156
  - Honest social proof only — no inflated numbers from seeder data
