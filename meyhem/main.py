import os, uuid, json, asyncio
import httpx, duckdb
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from dataclasses import dataclass
from time import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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

class ProviderRouter:
    "Fan out searches to multiple providers, merge, dedupe, and rank"
    def __init__(self, providers, db=None, hist_weight=0.7):
        self.providers,self.db,self.hist_weight = providers,db,hist_weight

    async def search(self, query, max_results=10):
        "Search all providers in parallel, merge and rank results"
        all_results = await asyncio.gather(*[p.search(query, max_results) for p in self.providers])
        merged = {}
        for results in all_results:
            for r in results:
                if r.url not in merged or r.score > merged[r.url].score: merged[r.url] = r
        if self.db: self._apply_historical(merged)
        ranked = sorted(merged.values(), key=lambda r: r.score, reverse=True)
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

db = init_db('meyhem.db')
router = ProviderRouter([ExaProvider(os.environ['EXA_API_KEY'])], db=db)
sessions = SessionManager()

class SearchReq(BaseModel):
    query: str
    max_results: int = 10
    session_id: str | None = None
    agent_id: str | None = None
    include_content: bool = False

class SelectReq(BaseModel):
    url: str
    position: int
    provider: str
    token_count: int | None = None
    is_terminal: bool = False

class OutcomeReq(BaseModel):
    success: bool
    selection_id: str | None = None
    signal_type: str = 'explicit'
    metadata: dict | None = None

app = FastAPI(title='Project Meyhem')

@app.post('/search')
async def api_search(req: SearchReq):
    sid = sessions.get_session(req.session_id, req.agent_id)
    results = await router.search(req.query, req.max_results)
    if not req.include_content:
        for r in results: r.content = None
    search_id = log_search(db, req.query, results, sid, req.agent_id)
    sessions.add_search(sid, search_id)
    return dict(search_id=search_id, session_id=sid, results=[r.__dict__ for r in results])

@app.post('/search/{search_id}/select')
async def api_select(search_id: str, req: SelectReq):
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        raise HTTPException(404, 'Search not found')
    content = await router.providers[0].fetch_content(req.url) if not req.is_terminal else None
    sel_id = log_selection(db, search_id, req.url, req.position, req.provider, req.token_count, req.is_terminal)
    return dict(selection_id=sel_id, content=content)

@app.post('/search/{search_id}/outcome')
async def api_outcome(search_id: str, req: OutcomeReq):
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        raise HTTPException(404, 'Search not found')
    oid = log_outcome(db, search_id, req.success, req.signal_type, req.selection_id, req.metadata)
    return dict(outcome_id=oid)

mcp = FastMCP("Project Meyhem", instructions="Agent-native search with feedback-driven ranking")

@mcp.tool()
async def search(query: str, max_results: int = 10, session_id: str = None, agent_id: str = None, include_content: bool = False) -> dict:
    "Search the web and return ranked results with feedback-driven scoring"
    sid = sessions.get_session(session_id, agent_id)
    results = await router.search(query, max_results)
    if not include_content:
        for r in results: r.content = None
    search_id = log_search(db, query, results, sid, agent_id)
    sessions.add_search(sid, search_id)
    return dict(search_id=search_id, session_id=sid, results=[r.__dict__ for r in results])

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
    "Report whether a search result helped complete your task"
    if not db.execute("SELECT 1 FROM searches WHERE id=?", [search_id]).fetchone():
        return dict(error='Search not found')
    oid = log_outcome(db, search_id, success, signal_type, selection_id, metadata)
    return dict(outcome_id=oid)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("meyhem:app", host="0.0.0.0", port=5001)
