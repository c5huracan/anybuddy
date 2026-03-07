import os, hashlib, uuid, json, asyncio, secrets, re
import mistletoe
from scalar_fastapi import get_scalar_api_reference
import httpx, duckdb
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from dataclasses import dataclass
from time import time
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

@dataclass
class SearchResult:
    "A single search result with optional content and historical signal"
    url: str
    title: str
    snippet: str
    token_count: int
    content_format: str
    provider: str
    source_domain: str
    score: float = 0.0
    content: str | None = None
    published_date: str | None = None
    historical_success: float | None = None

def init_db(path='meyhem.db'):
    "Create signal store tables, return connection"
    db = duckdb.connect(str(path))
    db.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id VARCHAR PRIMARY KEY, session_id VARCHAR, agent_id VARCHAR,
            query VARCHAR NOT NULL, results JSON, result_count INTEGER,
            providers JSON, created_at TIMESTAMP DEFAULT current_timestamp);
        CREATE TABLE IF NOT EXISTS selections (
            id VARCHAR PRIMARY KEY, search_id VARCHAR REFERENCES searches(id),
            url VARCHAR NOT NULL, position INTEGER, provider VARCHAR,
            token_count INTEGER, is_terminal BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp);
        CREATE TABLE IF NOT EXISTS outcomes (
            id VARCHAR PRIMARY KEY, search_id VARCHAR REFERENCES searches(id),
            selection_id VARCHAR REFERENCES selections(id), success BOOLEAN,
            signal_type VARCHAR, metadata JSON,
            created_at TIMESTAMP DEFAULT current_timestamp);
    """)
    return db

def log_search(db, query, results, session_id=None, agent_id=None):
    "Log a search and its results, return search id"
    sid = str(uuid.uuid4())
    db.execute("INSERT INTO searches VALUES (?,?,?,?,?,?,?,current_timestamp)",
        [sid, session_id, agent_id, query, json.dumps([r.__dict__ for r in results]),
         len(results), json.dumps(list({r.provider for r in results}))])
    return sid

def log_selection(db, search_id, url, position, provider, token_count=None, is_terminal=False):
    "Log a result selection, return selection id"
    sid = str(uuid.uuid4())
    db.execute("INSERT INTO selections VALUES (?,?,?,?,?,?,?,current_timestamp)",
        [sid, search_id, url, position, provider, token_count, is_terminal])
    return sid

def log_outcome(db, search_id, success, signal_type='explicit', selection_id=None, metadata=None):
    "Log an outcome signal, return outcome id"
    oid = str(uuid.uuid4())
    db.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,current_timestamp)",
        [oid, search_id, selection_id, success, signal_type, json.dumps(metadata) if metadata else None])
    return oid

class SearchProvider(ABC):
    "Base class for search providers"
    name: str
    @abstractmethod
    async def search(self, query, max_results=10) -> list[SearchResult]: ...
    @abstractmethod
    async def fetch_content(self, url) -> str: ...

class ExaProvider(SearchProvider):
    "Exa.ai search provider"
    name = 'exa'
    base_url = 'https://api.exa.ai'

    def __init__(self, api_key): self.api_key = api_key

    def _headers(self): return {'x-api-key': self.api_key, 'content-type': 'application/json'}

    def _to_result(self, r):
        domain = urlparse(r['url']).netloc
        txt = r.get('text', '')
        return SearchResult(url=r['url'], title=r.get('title', '').replace('\u00b6', '').strip(), snippet=txt[:200],
            token_count=len(txt)//4, content_format='text', provider=self.name,
            source_domain=domain, score=r.get('score', 0.0), content=txt or None,
            published_date=r.get('publishedDate'))

    async def search(self, query, max_results=10):
        "Search Exa and return list of SearchResults"
        async with httpx.AsyncClient() as c:
            resp = await c.post(f'{self.base_url}/search', headers=self._headers(),
                json=dict(query=query, numResults=max_results, type='neural', useAutoprompt=True,
                          contents=dict(text=True)))
            resp.raise_for_status()
        return [self._to_result(r) for r in resp.json()['results']]

    async def fetch_content(self, url):
        "Fetch full content for a URL via Exa contents endpoint"
        async with httpx.AsyncClient() as c:
            resp = await c.post(f'{self.base_url}/contents', headers=self._headers(),
                json=dict(urls=[url], text=dict(maxCharacters=10000)))
            resp.raise_for_status()
        results = resp.json().get('results', [])
        return results[0].get('text', '') if results else ''


class TavilyProvider(SearchProvider):
    "Tavily search provider — AI-optimized results"
    name = 'tavily'
    base_url = 'https://api.tavily.com/search'

    def __init__(self, api_key): self.api_key = api_key

    def _to_result(self, r, i):
        domain = urlparse(r['url']).netloc
        txt = r.get('content', '')
        return SearchResult(url=r['url'], title=r.get('title', ''), snippet=txt[:200],
            token_count=len(txt)//4, content_format='text', provider=self.name,
            source_domain=domain, score=1.0 - (i * 0.05), content=txt or None)

    async def search(self, query, max_results=10):
        async with httpx.AsyncClient() as c:
            resp = await c.post(self.base_url, json=dict(api_key=self.api_key, query=query,
                max_results=max_results, search_depth='basic', include_answer=False))
            resp.raise_for_status()
        return [self._to_result(r, i) for i, r in enumerate(resp.json().get('results', []))]

    async def fetch_content(self, url):
        async with httpx.AsyncClient() as c:
            resp = await c.post('https://api.tavily.com/extract', json=dict(api_key=self.api_key, urls=[url]))
            resp.raise_for_status()
        results = resp.json().get('results', [])
        return results[0].get('raw_content', '') if results else ''

class ProviderRouter:
    "Fan out searches to multiple providers, merge, dedupe, and rank"
    def __init__(self, providers, db=None, hist_weight=0.7, cache_ttl=300):
        self.providers,self.db,self.hist_weight,self.cache_ttl = providers,db,hist_weight,cache_ttl
        self.cache = {}

    def _cache_key(self, query): return query.strip().lower()

    def _cache_get(self, key):
        if key not in self.cache: return None
        results, ts = self.cache[key]
        if time() - ts > self.cache_ttl:
            del self.cache[key]
            return None
        return results

    async def search(self, query, max_results=10):
        "Search all providers in parallel, merge and rank results"
        key = self._cache_key(query)
        cached = self._cache_get(key)
        if cached: return cached[:max_results]
        all_results = await asyncio.gather(*[p.search(query, max_results) for p in self.providers], return_exceptions=True)
        all_results = [r for r in all_results if isinstance(r, list)]
        merged = {}
        for results in all_results:
            if not results: continue
            max_s, min_s = max(r.score for r in results), min(r.score for r in results)
            rng = max_s - min_s if max_s != min_s else 1.0
            for r in results:
                r.score = (r.score - min_s) / rng
                if r.url not in merged or r.score > merged[r.url].score: merged[r.url] = r
        if self.db: self._apply_historical(merged)
        ranked = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        self.cache[key] = (ranked, time())
        return ranked[:max_results]

    def _apply_historical(self, merged):
        "Blend historical success rates into scores"
        for url, r in merged.items():
            hist = self._get_success_rate(url)
            if hist is not None:
                r.historical_success = hist
                r.score = self.hist_weight * hist + (1 - self.hist_weight) * r.score

    def _get_success_rate(self, url):
        "Query DuckDB for historical success rate of a URL"
        row = self.db.execute("""
            SELECT avg(o.success::int) FROM outcomes o
            JOIN selections s ON o.selection_id = s.id
            WHERE s.url = ? AND o.signal_type != 'ambiguous'
        """, [url]).fetchone()
        return row[0] if row and row[0] is not None else None

class SessionManager:
    "Manage agent sessions with hybrid timeout + declared end"
    def __init__(self, timeout=300): self.timeout,self.sessions = timeout,{}

    def get_session(self, session_id=None, agent_id=None):
        "Get or create a session, return session_id"
        if session_id and session_id in self.sessions:
            self.touch(session_id)
            return session_id
        sid = session_id or str(uuid.uuid4())
        self.sessions[sid] = dict(agent_id=agent_id, created_at=time(), last_active=time(), closed=False, searches=[])
        return sid

    def touch(self, session_id):
        "Update last_active timestamp"
        if session_id in self.sessions: self.sessions[session_id]['last_active'] = time()

    def add_search(self, session_id, search_id):
        "Associate a search with a session"
        if session_id in self.sessions: self.sessions[session_id]['searches'].append(search_id)

    def close(self, session_id):
        "Explicitly close a session"
        if session_id in self.sessions: self.sessions[session_id]['closed'] = True

    def is_active(self, session_id):
        "Check if session is still active"
        s = self.sessions.get(session_id)
        if not s or s['closed']: return False
        return (time() - s['last_active']) < self.timeout

    def close_expired(self):
        "Close all timed-out sessions, return list of closed session ids"
        now = time()
        expired = [sid for sid,s in self.sessions.items() if not s['closed'] and (now - s['last_active']) >= self.timeout]
        for sid in expired: self.sessions[sid]['closed'] = True
        return expired

def _similar_query(q1, q2, threshold=0.5):
    w1, w2 = set(q1.lower().split()), set(q2.lower().split())
    if not w1 or not w2: return False
    return len(w1 & w2) / len(w1 | w2) >= threshold

def infer_outcomes(db, session_id):
    "Infer success/failure for searches in a closed session based on behavioral signals"
    searches = db.execute(
        "SELECT id, query, created_at FROM searches WHERE session_id=? ORDER BY created_at", [session_id]).fetchall()
    if not searches: return []
    inferred = []
    for i, (sid, query, ts) in enumerate(searches):
        sels = db.execute("SELECT id, is_terminal FROM selections WHERE search_id=? ORDER BY created_at", [sid]).fetchall()
        has_explicit = db.execute("SELECT 1 FROM outcomes WHERE search_id=? AND signal_type='explicit'", [sid]).fetchone()
        if has_explicit: continue
        has_next_search = i < len(searches) - 1
        next_query = searches[i+1][1] if has_next_search else None
        has_terminal = any(t for _, t in sels)
        if has_terminal: inferred.append((sid, True, 'terminal_selection'))
        elif not sels: inferred.append((sid, False, 'no_selection'))
        elif has_next_search and _similar_query(query, next_query): inferred.append((sid, False, 'reformulated_query'))
        elif not has_next_search and sels: inferred.append((sid, True, 'no_reformulation'))
        else: inferred.append((sid, None, 'ambiguous'))
    for sid, success, signal in inferred:
        if success is not None: log_outcome(db, sid, success, signal_type=f'inferred_{signal}')
    return inferred

from pathlib import Path as P
P('data').mkdir(exist_ok=True)
db = init_db('data/meyhem.db')

def init_index(path='data/mcp_index.db'):
    import shutil
    src = os.path.join(os.path.dirname(__file__), 'mcp_index.db')
    if os.path.exists(src): shutil.copy(src, path)
    idx = duckdb.connect(str(path))
    idx.execute('INSTALL fts; LOAD fts')
    idx.execute("PRAGMA create_fts_index('servers', 'url', 'name', 'description', 'category', overwrite=1)")
    return idx

idx = init_index()

router = ProviderRouter([ExaProvider(os.environ['EXA_API_KEY']), TavilyProvider(os.environ['TAVILY_API_KEY'])], db=db)
sessions = SessionManager()
db.execute('CREATE TABLE IF NOT EXISTS reports (id VARCHAR PRIMARY KEY, search_id VARCHAR, query VARCHAR, html TEXT, md TEXT, created_at TIMESTAMP DEFAULT current_timestamp)')
db.execute('CREATE TABLE IF NOT EXISTS page_views (path VARCHAR, ts TIMESTAMP DEFAULT current_timestamp)')


class SearchResultItem(BaseModel):
    "A single search result"
    url: str = Field(description="URL of the result")
    title: str = Field(description="Page title")
    snippet: str = Field(description="Text preview (first ~200 chars)")
    token_count: int = Field(description="Estimated token count of full content")
    content_format: str = Field(description="Content format (e.g. 'text')")
    provider: str = Field(description="Which search engine returned this result")
    source_domain: str = Field(description="Domain of the result URL")
    score: float = Field(description="Relevance score (0-1)")
    content: str | None = Field(None, description="Full page content (only if include_content=true)")
    published_date: str | None = Field(None, description="Publication date if available")
    historical_success: float | None = Field(None, description="Historical performance for this URL, null if no prior data")

class SearchResp(BaseModel):
    "Search response with ranked results"
    search_id: str = Field(description="Unique ID for this search (use in /select and /outcome)")
    session_id: str = Field(description="Session ID for grouping related searches")
    results: list[SearchResultItem] = Field(description="Ranked search results")
    outcome_endpoint: str = Field(description="POST outcome here when your task completes")
    outcome_hint: str = Field(description="How to report outcomes")

class SelectResp(BaseModel):
    "Selection response with full content"
    selection_id: str = Field(description="Unique ID for this selection (use in /outcome)")
    content: str | None = Field(description="Full page content, or null if is_terminal=true")

class OutcomeResp(BaseModel):
    "Outcome confirmation"
    outcome_id: str = Field(description="Unique ID for the recorded outcome")

class SearchReq(BaseModel):
    "Search the web and get ranked results"
    query: str = Field(description="Search query string")
    max_results: int = Field(10, description="Maximum number of results to return (1-20)")
    session_id: str | None = Field(None, description="Optional session ID to group related searches")
    agent_id: str | None = Field(None, description="Optional identifier for the calling agent")
    include_content: bool = Field(False, description="If true, include full page content in results (increases response size)")
    model_config = dict(json_schema_extra=dict(examples=[dict(query="python asyncio best practices", max_results=5)]))

class SelectReq(BaseModel):
    "Select a search result to retrieve its full content"
    url: str = Field(description="URL of the selected result")
    position: int = Field(description="Zero-based position of the result in the search response")
    provider: str = Field(description="Provider that returned this result (from the result object)")
    token_count: int | None = Field(None, description="Optional token count of content consumed by your agent")
    is_terminal: bool = Field(False, description="Set true if this is the final selection (skips content fetch)")
    model_config = dict(json_schema_extra=dict(examples=[dict(url="https://example.com/article", position=0, provider="exa")]))

class OutcomeReq(BaseModel):
    "Report whether a selected result helped complete your task"
    success: bool = Field(description="True if the result helped complete the task, false otherwise")
    selection_id: str | None = Field(None, description="ID of the specific selection this outcome refers to")
    signal_type: str = Field('explicit', description="How the signal was generated")
    metadata: dict | None = Field(None, description="Optional metadata about the outcome")
    model_config = dict(json_schema_extra=dict(examples=[dict(success=True, selection_id="abc-123")]))

from fastapi.responses import HTMLResponse
from starlette.responses import JSONResponse, Response

mcp = FastMCP("Project Meyhem", instructions="Agent-native search with feedback-driven ranking", streamable_http_path="/", host="0.0.0.0")

@mcp.tool()
async def search(query: str, max_results: int = 10, session_id: str = None, agent_id: str = None, include_content: bool = False) -> dict:
    "Search the web and return ranked results with feedback-driven scoring. IMPORTANT: after using results, call the outcome tool with the search_id and success=true/false to improve future rankings."
    sid = sessions.get_session(session_id, agent_id)
    results = await router.search(query, max_results)
    if not include_content:
        for r in results: r.content = None
    search_id = log_search(db, query, results, sid, agent_id)
    sessions.add_search(sid, search_id)
    return dict(search_id=search_id, session_id=sid, results=[r.__dict__ for r in results],
        outcome_endpoint=f'/search/{search_id}/outcome',
        outcome_hint='After using results, POST {"success": true/false} to the outcome_endpoint to improve future rankings.')

@mcp.tool()
async def select(search_id: str, url: str, position: int, provider: str, token_count: int = None, is_terminal: bool = False) -> dict:
    "Select a search result to get its full content"
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        return dict(error='Search not found')
    content = await router.providers[0].fetch_content(url) if not is_terminal else None
    sel_id = log_selection(db, search_id, url, position, provider, token_count, is_terminal)
    return dict(selection_id=sel_id, content=content)

@mcp.tool()
async def outcome(search_id: str, success: bool, selection_id: str = None, signal_type: str = 'explicit', metadata: dict = None) -> dict:
    "Report whether a search result helped complete your task. Call this after every search with success=true if results were useful, or success=false if not. This is what makes Meyhem rankings improve over time."
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        return dict(error='Search not found')
    oid = log_outcome(db, search_id, success, signal_type, selection_id, metadata)
    return dict(outcome_id=oid)

from contextlib import asynccontextmanager


@mcp.tool()
async def find_server(query: str, max_results: int = 5) -> dict:
    "Find MCP servers for a given task. Describe what you need in natural language."
    rows = idx.execute("""SELECT name, url, description, category, stars, language,
        fts_main_servers.match_bm25(url, ?) * (1 + ln(COALESCE(stars, 1) + 1)) AS score
        FROM servers WHERE fts_main_servers.match_bm25(url, ?) IS NOT NULL
        ORDER BY score DESC LIMIT ?""", [query, query, max_results]).fetchall()
    return dict(results=[dict(name=r[0], url=r[1], description=r[2], category=r[3], stars=r[4], language=r[5], score=round(r[6], 2)) for r in rows])

mcp_starlette_app = mcp.streamable_http_app()

async def _cleanup_loop():
    while True:
        await asyncio.sleep(60)
        try:
            expired = sessions.close_expired()
            for sid in expired: infer_outcomes(db, sid)
        except: pass

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_cleanup_loop())
    async with mcp.session_manager.run():
        yield
    task.cancel()

app = FastAPI(docs_url=None, title='Project Meyhem', version='0.1.0', description='Better search results for your AI tools. Results improve with usage.', lifespan=lifespan)

@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    from scalar_fastapi import AgentScalarConfig
    return get_scalar_api_reference(
        openapi_url=app.openapi_url, title="Project Meyhem",
        scalar_favicon_url="",
        dark_mode=True, hide_dark_mode_toggle=False,
        show_developer_tools='never',
        agent=AgentScalarConfig(disabled=True),
        telemetry=False,
        custom_css="""
.light-mode, .dark-mode {
  --scalar-color-accent: #89bf04;
  --scalar-background-accent: #2a3a10;
}
""")

@app.get('/calibrate', include_in_schema=False)
async def calibrate(request: Request):
    if request.headers.get('authorization') != f'Bearer {os.environ.get("STATS_KEY", "")}': raise HTTPException(401, 'Unauthorized')
    rows = db.execute("""
        SELECT o_inf.search_id, o_inf.signal_type, o_inf.success as inferred, o_exp.success as explicit
        FROM outcomes o_inf JOIN outcomes o_exp ON o_inf.search_id = o_exp.search_id
        WHERE o_inf.signal_type LIKE 'inferred_%' AND o_exp.signal_type = 'explicit'
    """).fetchall()
    if not rows: return dict(total=0, message='No calibration data yet')
    by_rule = {}
    for _, signal, inferred, explicit in rows:
        rule = signal.replace('inferred_', '')
        if rule not in by_rule: by_rule[rule] = dict(correct=0, total=0)
        by_rule[rule]['total'] += 1
        if inferred == explicit: by_rule[rule]['correct'] += 1
    for rule, d in by_rule.items(): d['accuracy'] = d['correct'] / d['total'] if d['total'] else 0
    correct = sum(d['correct'] for d in by_rule.values())
    return dict(total=len(rows), overall_accuracy=correct/len(rows), rules=by_rule)

app.mount('/mcp', mcp_starlette_app)


from starlette.responses import PlainTextResponse



@app.get('/sitemap.xml', include_in_schema=False)
async def sitemap():
    rows = db.execute("SELECT id, created_at FROM reports ORDER BY created_at DESC").fetchall()
    urls = ['<url><loc>https://api.rhdxm.com/</loc><priority>1.0</priority></url>',
            '<url><loc>https://api.rhdxm.com/docs</loc><priority>0.8</priority></url>',
            '<url><loc>https://api.rhdxm.com/research</loc><priority>0.8</priority></url>']
    for rid, ts in rows:
        urls.append(f'<url><loc>https://api.rhdxm.com/r/{rid}</loc><lastmod>{str(ts)[:10]}</lastmod><priority>0.6</priority></url>')
    return Response(f"""<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{''.join(urls)}</urlset>""", media_type='application/xml')

@app.get('/robots.txt', include_in_schema=False, response_class=PlainTextResponse)
async def robots_txt(): return open('robots.txt').read()

@app.get('/llms.txt', include_in_schema=False, response_class=PlainTextResponse)
async def llms_txt(): return open('llms.txt').read()

@app.get('/', include_in_schema=False, response_class=HTMLResponse)
async def landing(): return open('landing.html').read()


class RateLimiter:
    "Per-IP sliding window rate limiter"
    def __init__(self, rpm=20, burst=5):
        self.rpm,self.burst,self.requests = rpm,burst,{}

    def _cleanup(self, ip, now):
        if ip in self.requests: self.requests[ip] = [t for t in self.requests[ip] if now - t < 60]

    def check(self, ip):
        now = time()
        self._cleanup(ip, now)
        reqs = self.requests.get(ip, [])
        if len(reqs) >= self.rpm: return False
        if len(reqs) >= self.burst and reqs[-1] - reqs[-self.burst] < 2: return False
        self.requests.setdefault(ip, []).append(now)
        return True

limiter = RateLimiter()
research_limiter = RateLimiter(rpm=3, burst=2)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/", "/docs", "/openapi.json") or request.url.path.startswith("/mcp"):
        if request.url.path in ("/", "/docs"): db.execute("INSERT INTO page_views VALUES (?, current_timestamp)", [request.url.path])
        return await call_next(request)
    ip = request.client.host
    if request.headers.get('authorization') == f'Bearer {os.environ.get("STATS_KEY", "")}': return await call_next(request)
    if not limiter.check(ip): return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    if request.url.path == '/research/generate' and not research_limiter.check(ip): return JSONResponse(status_code=429, content={"detail": "Research rate limit exceeded: max 3/min"})
    return await call_next(request)

@app.post('/search', summary='Search', response_model=SearchResp, description='Query multiple search engines and get ranked results.')
async def api_search(req: SearchReq, request: Request):
    if not req.agent_id: req.agent_id = f"anon-{hashlib.sha256(f'meyhem-{request.client.host}'.encode()).hexdigest()[:8]}"
    sid = sessions.get_session(req.session_id, req.agent_id)
    results = await router.search(req.query, req.max_results)
    if not req.include_content:
        for r in results: r.content = None
    search_id = log_search(db, req.query, results, sid, req.agent_id)
    sessions.add_search(sid, search_id)
    return dict(search_id=search_id, session_id=sid, results=[r.__dict__ for r in results],
        outcome_endpoint=f'/search/{search_id}/outcome',
        outcome_hint='After using results, POST {"success": true/false} to the outcome_endpoint to improve future rankings.')

@app.post('/search/{search_id}/select', summary='Select a result', response_model=SelectResp, description='Pick a result from a previous search to retrieve its full content. Logs the selection for ranking improvement.')
async def api_select(search_id: str, req: SelectReq):
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        raise HTTPException(404, 'Search not found')
    content = await router.providers[0].fetch_content(req.url) if not req.is_terminal else None
    sel_id = log_selection(db, search_id, req.url, req.position, req.provider, req.token_count, req.is_terminal)
    return dict(selection_id=sel_id, content=content)

@app.post('/search/{search_id}/outcome', summary='Report outcome', response_model=OutcomeResp, description='Report whether a search result helped complete your task. Helps improve future results.')
async def api_outcome(search_id: str, req: OutcomeReq):
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        raise HTTPException(404, 'Search not found')
    oid = log_outcome(db, search_id, req.success, req.signal_type, req.selection_id, req.metadata)
    return dict(outcome_id=oid)



class FindReq(BaseModel):
    query: str = Field(description="Describe what you need, e.g. 'I need to query a Postgres database'")
    max_results: int = Field(5, description="Number of results (1-20)")

@app.post('/find', summary='Find MCP servers', description='Find the right MCP server for your task.')
async def api_find(req: FindReq):
    rows = idx.execute("""SELECT name, url, description, category, stars, language,
        fts_main_servers.match_bm25(url, ?) * (1 + ln(COALESCE(stars, 1) + 1)) AS score
        FROM servers WHERE fts_main_servers.match_bm25(url, ?) IS NOT NULL
        ORDER BY score DESC LIMIT ?""", [req.query, req.query, req.max_results]).fetchall()
    return dict(results=[dict(name=r[0], url=r[1], description=r[2], category=r[3], stars=r[4], language=r[5], score=round(r[6], 2)) for r in rows])

@app.get('/health', summary='Health check', response_model=dict)
async def health():
    try: db.execute("SELECT 1").fetchone(); db_ok = True
    except: db_ok = False
    return dict(status='ok' if db_ok else 'degraded', db=db_ok, version='0.1.0')

@app.get('/stats/corpus', include_in_schema=False)
async def stats_corpus(request: Request):
    if request.headers.get('authorization') != f'Bearer {os.environ.get("STATS_KEY", "")}': raise HTTPException(401, 'Unauthorized')
    urls = db.execute("SELECT COUNT(DISTINCT url) FROM selections").fetchone()[0]
    domains = db.execute("SELECT COUNT(DISTINCT split_part(url, '/', 3)) FROM selections").fetchone()[0]
    with_outcomes = db.execute("SELECT COUNT(DISTINCT s.url) FROM selections s JOIN outcomes o ON o.selection_id = s.id").fetchone()[0]
    successful = db.execute("SELECT COUNT(DISTINCT s.url) FROM selections s JOIN outcomes o ON o.selection_id = s.id WHERE o.success = true").fetchone()[0]
    top_domains = db.execute("SELECT split_part(url, '/', 3) as domain, COUNT(*) as n, COUNT(DISTINCT url) as unique_urls FROM selections GROUP BY domain ORDER BY n DESC LIMIT 20").fetchall()
    return dict(unique_urls=urls, unique_domains=domains, urls_with_outcomes=with_outcomes, urls_successful=successful, top_domains=[dict(domain=d, selections=n, unique_urls=u) for d,n,u in top_domains])
@app.get('/stats', include_in_schema=False)
async def stats(request: Request):
    if request.headers.get('authorization') != f'Bearer {os.environ.get("STATS_KEY", "")}': raise HTTPException(401, 'Unauthorized')
    searches = db.execute("SELECT count(*), count(DISTINCT agent_id) FROM searches").fetchone()
    selections = db.execute("SELECT count(*) FROM selections").fetchone()
    outcomes = db.execute("SELECT count(*) FROM outcomes").fetchone()
    agents = db.execute("SELECT agent_id, count(*) as n FROM searches GROUP BY agent_id ORDER BY n DESC").fetchall()
    views = {r[0]: r[1] for r in db.execute("SELECT path, count(*) FROM page_views GROUP BY path").fetchall()}
    return dict(page_views=views, total_searches=searches[0], unique_agents=searches[1], total_selections=selections[0],
        total_outcomes=outcomes[0], agents=[dict(agent_id=a, count=n) for a,n in agents])





@app.get('/stats/queries', include_in_schema=False)
async def stats_queries(request: Request, agent_id: str = None, limit: int = 50):
    if request.headers.get('authorization') != f'Bearer {os.environ.get("STATS_KEY", "")}': raise HTTPException(401, 'Unauthorized')
    if agent_id:
        rows = db.execute("SELECT query, agent_id, created_at FROM searches WHERE agent_id=? ORDER BY created_at DESC LIMIT ?", [agent_id, limit]).fetchall()
    else:
        rows = db.execute("SELECT query, agent_id, created_at FROM searches ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
    return [dict(query=q, agent_id=a, created_at=str(t)) for q,a,t in rows]


def _postprocess_report(html, sources):
    from urllib.parse import urlparse
    parts = html.split('<h2>Sources</h2>')
    body = parts[0]
    for i, s in enumerate(sources, 1):
        body = body.replace(f'[{i}]', f'<a href="#{i}" class="cite">[{i}]</a>')
    src_html = '<h2>Sources</h2><ol class="sources">'
    for i, s in enumerate(sources, 1):
        domain = urlparse(s['url']).netloc.replace('www.', '')
        title = s.get('title', domain)
        src_html += f'<li id="{i}"><a href="{s["url"]}" target="_blank">{title}</a> <span class="domain">({domain})</span></li>'
    src_html += '</ol>'
    return body + src_html

def _render_report(query, html):
    desc = re.sub('<[^>]+>', '', html[:200]).strip()
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:title" content="Meyhem Research: {query}">
<meta property="og:description" content="{desc}">
<style>
  body {{ max-width:680px; margin:40px auto; padding:0 20px; font-family:system-ui,-apple-system,sans-serif; line-height:1.6; color:#e8e8e8; background:#1a1a2e; }}
  h1 {{ font-size:1.5em; border-bottom:2px solid #89bf04; padding-bottom:8px; }}
  h2 {{ font-size:1.2em; }}
  code {{ background:#16213e; padding:2px 6px; border-radius:3px; font-size:0.9em; color:#89bf04; }}
  a {{ color:#5b9bf7; }} a.cite {{ color:#89bf04; text-decoration:none; font-size:0.85em; vertical-align:super; }}
  strong {{ color:#fff; }}
  ol.sources {{ padding-left:1.5em; }} ol.sources li {{ margin:6px 0; }} .domain {{ color:#666; font-size:0.85em; }}
  .footer {{ margin-top:40px; padding-top:16px; border-top:1px solid #333; font-size:0.85em; color:#888; }}
  .footer a {{ color:#89bf04; }}
  .share {{ margin-top:24px; }} .share button {{ padding:6px 16px; background:#89bf04; color:#1a1a2e; border:none; border-radius:4px; cursor:pointer; font-weight:bold; font-size:0.9em; }}
  .search-box {{ margin-top:20px; }}
  .search-box input {{ width:70%; padding:8px 12px; border:1px solid #333; border-radius:4px; background:#16213e; color:#e8e8e8; }}
  .search-box button {{ padding:8px 16px; background:#89bf04; color:#1a1a2e; border:none; border-radius:4px; cursor:pointer; font-weight:bold; }}
</style></head><body>
{html}
<script>document.querySelector('h1').style.display='flex';document.querySelector('h1').style.justifyContent='space-between';document.querySelector('h1').style.alignItems='center';document.querySelector('h1').insertAdjacentHTML('beforeend','<button onclick="navigator.clipboard.writeText(window.location.href).then(()=>this.textContent=\\'Copied!\\')" style="font-size:0.4em;padding:6px 16px;background:#89bf04;color:#1a1a2e;border:none;border-radius:4px;cursor:pointer;font-weight:bold;white-space:nowrap">Copy link</button>')</script>
<div class="footer">
  Powered by <a href="https://api.rhdxm.com">Meyhem</a>: agent-native search with feedback-driven ranking
  <div class="search-box"><form action="/research" method="get"><input name="q" placeholder="Research something else..."> <button type="submit">Go</button></form></div>
</div></body></html>"""

_RESEARCH_SP = "You are a research analyst. Given search results, write a concise 3-paragraph report with numbered citations [1][2] etc. End with a Sources section listing each URL. Be factual and direct."

@app.get('/research', include_in_schema=False, response_class=HTMLResponse)
async def research(q: str = None):
    if not q: return HTMLResponse('<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body { max-width:680px; margin:100px auto; padding:0 20px; font-family:system-ui,sans-serif; color:#e8e8e8; background:#1a1a2e; text-align:center; } input { width:70%; padding:12px 16px; border:2px solid #89bf04; border-radius:4px; background:#16213e; color:#e8e8e8; font-size:1em; } button { padding:12px 24px; background:#89bf04; color:#1a1a2e; border:none; border-radius:4px; font-weight:700; cursor:pointer; font-size:1em; } h1 { color:#89bf04; }</style></head><body><h1>Meyhem Research</h1><p>Enter a topic to generate a cited research report.</p><form action="/research" method="get" style="margin-top:24px; display:flex; gap:8px; justify-content:center;"><input name="q" placeholder="e.g. best MCP tools for sales automation"><button type="submit">Research</button></form></body></html>')
    return HTMLResponse(f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body {{ max-width:680px; margin:100px auto; padding:0 20px; font-family:system-ui,-apple-system,sans-serif; color:#e8e8e8; background:#1a1a2e; text-align:center; }}
.spinner {{ display:inline-block; width:40px; height:40px; border:3px solid #333; border-top:3px solid #89bf04; border-radius:50%; animation:spin 1s linear infinite; }}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }} p {{ margin-top:20px; color:#888; }}</style></head>
<body><div class="spinner"></div><p>Researching...</p>
<script>fetch("/research/generate?q="+encodeURIComponent("{q}")).then(r=>r.json()).then(d=>window.location=d.url).catch(()=>document.querySelector("p").textContent="Something went wrong. Try again.")</script>
</body></html>''')

_DECOMPOSE_SP = "Break this research question into 3-4 focused search queries. Return ONLY a JSON list of strings."

async def _decompose(q):
    chat = Chat('claude-sonnet-4-20250514', sp=_DECOMPOSE_SP)
    r = await asyncio.to_thread(chat, f"Break into 3 targeted search queries:\n{q}")
    txt = r.content[0].text
    m = __import__('re').search(r'\[.*\]', txt, __import__('re').DOTALL)
    return __import__('json').loads(m.group()) if m else [q]

@app.get('/research/generate', include_in_schema=False)
async def research_generate(q: str):
    existing = db.execute("SELECT id FROM reports WHERE query=? ORDER BY created_at DESC LIMIT 1", [q]).fetchone()
    if existing: return dict(url=f'/r/{existing[0]}')
    sid = sessions.get_session(agent_id='research')
    queries = await _decompose(q)
    all_results, search_ids = [], []
    for sub_q in queries:
        results = await router.search(sub_q, 10)
        search_id = log_search(db, sub_q, results, sid, 'research')
        search_ids.append(search_id)
        all_results.extend(results)
    seen = set()
    deduped = [r for r in all_results if r.url not in seen and not seen.add(r.url)]
    listing = "\n".join(f"{i}. {r.title} ({r.url})" for i,r in enumerate(deduped))
    select_chat = Chat('claude-sonnet-4-20250514', sp="Pick the 8 most relevant results for a research question. Return ONLY a JSON list of integer indices.")
    sel_r = await asyncio.to_thread(select_chat, f"Question: {q}\n\nResults:\n{listing}")
    sel_txt = sel_r.content[0].text
    sel_m = __import__('re').search(r'\[.*\]', sel_txt, __import__('re').DOTALL)
    idxs = __import__('json').loads(sel_m.group()) if sel_m else list(range(min(8, len(deduped))))
    selected = [deduped[i] for i in idxs if i < len(deduped)]
    sources_txt = "\n\n".join(f"[{i}] {r.title}\nURL: {r.url}\n{(r.content or '')[:1500]}" for i,r in enumerate(selected, 1))
    chat = Chat('claude-sonnet-4-20250514', sp=_RESEARCH_SP)
    md = (await asyncio.to_thread(chat, f"Query: {q}\n\nSources:\n{sources_txt}\n\nWrite a research report.")).content[0].text
    html = _postprocess_report(mistletoe.markdown(md), [dict(url=r.url, title=r.title) for r in selected])
    rid = secrets.token_urlsafe(6)
    db.execute("INSERT INTO reports VALUES (?,?,?,?,?,current_timestamp)", [rid, search_ids[0], q, html, md])
    for r in selected:
        try: db.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,current_timestamp)", [search_ids[0], r.url, True, 'research', 'Used in research report'])
        except: pass
    return dict(url=f'/r/{rid}')

@app.get('/r/{rid}', include_in_schema=False, response_class=HTMLResponse)
async def get_report(rid: str):
    row = db.execute("SELECT query, html FROM reports WHERE id=?", [rid]).fetchone()
    if not row: raise HTTPException(404, 'Report not found')
    return _render_report(row[0], row[1])


@app.get('/stats/reports', include_in_schema=False)
async def stats_reports(request: Request, limit: int = 20):
    if request.headers.get('authorization') != f'Bearer {os.environ.get("STATS_KEY", "")}': raise HTTPException(401, 'Unauthorized')
    rows = db.execute("SELECT id, query, created_at FROM reports ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
    return [dict(id=i, query=q, url=f'/r/{i}', created_at=str(t)) for i,q,t in rows]

from claudette import Chat

discover_sp = "You are an MCP server discovery agent. Given search results about MCP servers, analyze them and return a JSON config block ready to paste into Claude Desktop or Cursor. Be concise."

class DiscoverReq(BaseModel):
    query: str = Field(description="Describe what you need, e.g. 'I need to interact with a SQLite database'")
    agent_id: str | None = Field(None, description="Optional agent identifier")

class DiscoverResp(BaseModel):
    answer: str = Field(description="Analysis and recommended MCP config")
    search_id: str = Field(description="ID of the underlying search")

def _run_discover(query, search_results):
    chat = Chat('claude-sonnet-4-20250514', sp=discover_sp)
    prompt = f"Query: {query}\n\nSearch results:\n{json.dumps(search_results, indent=2)}\n\nRecommend the best MCP server and provide a ready-to-paste JSON config."
    return chat(prompt).content[0].text

@app.post('/discover', summary='Discover MCP servers', response_model=DiscoverResp, description='Find the right MCP server for your needs. Uses AI to analyze search results and return a config.')
async def api_discover(req: DiscoverReq):
    sid = sessions.get_session(agent_id=req.agent_id)
    results = await router.search(f"MCP server {req.query}", 5)
    search_id = log_search(db, req.query, results, sid, req.agent_id)
    search_results = [dict(url=r.url, title=r.title, snippet=r.snippet) for r in results]
    answer = await asyncio.to_thread(_run_discover, req.query, search_results)
    return dict(answer=answer, search_id=search_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5001)
