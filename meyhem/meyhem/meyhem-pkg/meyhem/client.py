import httpx
from fastcore.utils import store_attr

class SearchResult:
    "Single search result from Meyhem"
    def __init__(self, url, title, snippet, score=0.0, source_domain=None, search_id=None, position=0, provider=None):
        store_attr()
    def __repr__(self): return f'SearchResult({self.title!r}, score={self.score:.2f})'
    def to_dict(self): return {k:v for k,v in self.__dict__.items() if v is not None}

class Meyhem:
    "Agent-native search client"
    def __init__(self, agent_id='default', base_url='https://api.rhdxm.com'):
        store_attr()
        self._client = httpx.Client(base_url=base_url, timeout=30)

    def search(self, query, num_results=5):
        "Search and return list of SearchResult"
        r = self._client.post('/search', json=dict(query=query, num_results=num_results, agent_id=self.agent_id))
        r.raise_for_status()
        data = r.json()
        self._last_search_id = data.get('search_id')
        fields = ('url','title','snippet','score','source_domain','provider')
        return [SearchResult(search_id=self._last_search_id, position=i, **{k:v for k,v in res.items() if k in fields})
                for i,res in enumerate(data.get('results', []))]

    def select(self, result):
        "Report that agent selected this result"
        r = self._client.post(f'/search/{result.search_id}/select', json=dict(url=result.url, position=result.position, provider=result.provider or ''))
        r.raise_for_status()
        return r.json()

    def report(self, result, success, details=None):
        "Report outcome for a search result"
        payload = dict(search_id=result.search_id, selected_url=result.url, success=success, agent_id=self.agent_id)
        if details: payload['details'] = details
        r = self._client.post(f'/search/{result.search_id}/outcome', json=payload)
        r.raise_for_status()
        return r.json()

    def discover(self, query):
        "Find the right MCP server for your needs"
        r = self._client.post('/discover', json=dict(query=query, agent_id=self.agent_id))
        r.raise_for_status()
        return r.json()

    def close(self): self._client.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
