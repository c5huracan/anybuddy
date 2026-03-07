from claudette import Chat
from meyhem import Meyhem
from fastcore.utils import store_attr, patch
import json

build_sp = """You are an expert Python developer. Given a task description and research results, write a complete, runnable Python script that accomplishes the task. Use the simplest approach: prefer stdlib and well-known libraries over MCP servers. Include a if __name__ == '__main__' block. Be concise."""

class MetaAgent:
    "Agent that builds agents: describe what you need, get a working script"
    def __init__(self, agent_id='meta-agent', model='claude-sonnet-4-20250514'):
        store_attr()
        self.m = Meyhem(agent_id)

    def research(self, task, num_searches=3):
        "Search Meyhem for approaches to accomplish the task"
        queries = [task, f"Python library for {task}", f"API for {task}"][:num_searches]
        results = {}
        for q in queries:
            try: results[q] = self.m.search(q)
            except: pass
        self._research = results
        return {q: [(r.title, r.url) for r in rs[:3]] for q,rs in results.items()}

    def build(self, task):
        "Generate a working agent script from research results"
        research_summary = json.dumps({q: [(r.title, r.url, r.snippet) for r in rs[:3]] for q,rs in self._research.items()}, indent=2)
        chat = Chat(self.model, sp=build_sp)
        prompt = f"Task: {task}\n\nResearch results:\n{research_summary}\n\nWrite a complete Python script."
        resp = chat(prompt)
        self._script = resp.content[0].text
        for q,rs in self._research.items():
            if rs: self.m.report(rs[0], True)
        return self._script

    def __call__(self, task):
        "Describe a task, get a working agent script"
        self.research(task)
        return self.build(task)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2: print("Usage: python meta_agent.py \'describe what you want\'"); sys.exit(1)
    ma = MetaAgent()
    print(ma(" ".join(sys.argv[1:])))
