# Meyhem API Endpoints (Complete)

## Public (in OpenAPI spec)
- POST /search — query multiple engines, get ranked results
- POST /search/{id}/select — pick a result, get full content
- POST /search/{id}/outcome — report success/failure
- GET /health — db check, version
- POST /discover — AI-powered MCP server discovery (slow, uses LLM)

## Protected (require Authorization: Bearer $STATS_KEY)
- GET /stats — overview: page_views, total_searches, unique_agents, agent list
- GET /stats/queries — recent queries, filterable with ?agent_id=
- GET /stats/corpus — unique URLs/domains, top domains by selections
- GET /stats/reports — generated research reports (id, query, url, created_at)
- GET /calibrate — inference accuracy vs explicit outcomes

## Public (not in schema)
- GET / — landing page HTML
- GET /docs — Scalar API docs
- GET /sitemap.xml
- GET /robots.txt
- GET /llms.txt
- GET /research — research UI (HTML)
- GET /research/generate — research generation
- GET /r/{rid} — research result page
