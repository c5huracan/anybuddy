# meyhem

Smart search for agents, however you build them.

## Install

```
pip install meyhem
```

## Quickstart

```python
from meyhem import Meyhem

m = Meyhem('my-agent')
res = m.search("Python testing frameworks")
m.select(res[0])
m.report(res[0], True)
```

## API

- `Meyhem(agent_id, base_url)` — create a client
- `m.search(query, num_results=5)` — returns list of `SearchResult`
- `m.select(result)` — report which result your agent picked
- `m.report(result, success, details=None)` — report if it worked

## SearchResult fields

`url`, `title`, `snippet`, `score`, `source_domain`, `provider`, `position`

## Context manager

```python
with Meyhem('my-agent') as m:
    res = m.search("best practices for async Python")
    print(res[0].title, res[0].score)
```

## Links

- **API docs**: https://api.rhdxm.com/docs
- **Homepage**: https://api.rhdxm.com
- **GitHub**: https://github.com/c5huracan/meyhem
