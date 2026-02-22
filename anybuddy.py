import os, re, sys, asyncio
import datetime as dt
from zoneinfo import ZoneInfo
from fastcore.utils import store_attr
from dialoghelper import find_msgs, add_msg, add_prompt, update_msg, dh_settings

def _cli_arg(name, default=None):
    for i,a in enumerate(sys.argv):
        if a == f'--{name}' and i+1 < len(sys.argv): return sys.argv[i+1]
    return default

DNAME = _cli_arg('dialog') or os.environ.get('ANYBUDDY_DIALOG', 'anybuddy-discord')
TZ = _cli_arg('tz') or os.environ.get('ANYBUDDY_TZ', 'US/Central')
VERBOSE = _cli_arg('verbose', '').lower() in ('1', 'true') or os.environ.get('ANYBUDDY_VERBOSE', '').lower() in ('1', 'true')

dh_settings['dname'] = DNAME
__dialog_name = DNAME

def log(*args):
    if VERBOSE: print(*args)

def format_output(output):
    output = re.sub(r"<details class='tool-usage-details'>\s*<summary>(.*?)</summary>.*?</details>", lambda m: f"🔧`{m.group(1)}`", output, flags=re.DOTALL)
    return re.sub(r'\n{3,}', '\n\n', output).strip('\n')

class Brain:
    "Base class for AI backends"
    async def send_prompt(self, text): raise NotImplementedError
    async def ensure_section(self): raise NotImplementedError
    async def hide_section(self, header): raise NotImplementedError

class SolveitBrain(Brain):
    "Solveit dialoghelper backend"
    def __init__(self, dname=DNAME, tz=TZ):
        store_attr()
        self._tz = ZoneInfo(tz)

    async def send_prompt(self, text): return await add_prompt(text, dname=self.dname, placement='at_end')

    async def hide_section(self, header):
        "Skip and collapse a section"
        msgs = await find_msgs(header_section=header, dname=self.dname)
        for m in msgs: await update_msg(id=m['id'], skipped=1, dname=self.dname)
        if msgs: await update_msg(id=msgs[0]['id'], heading_collapsed=1, dname=self.dname)

    async def ensure_section(self):
        "Create today's section, hide yesterday's"
        today = dt.datetime.now(self._tz).date().strftime('%a %d %b %Y')
        if (existing := await find_msgs(re_pattern=f"^## {today}$", dname=self.dname)): return existing[0]['id']
        for sec in await find_msgs(re_pattern=r"^## [A-Z][a-z]{2} \d{2} [A-Z][a-z]{2} \d{4}$", dname=self.dname):
            await self.hide_section(sec['content'])
        return await add_msg(f"## {today}", placement='at_end', dname=self.dname)

def _patch_anthropic():
    "Temp fix: anthropic 0.83 added web_fetch_requests but claudette 0.3.13 doesn't pass it"
    from anthropic.types import ServerToolUsage
    _orig_init = ServerToolUsage.__init__
    def _patched_init(self, **kw):
        kw.setdefault('web_fetch_requests', 0)
        _orig_init(self, **kw)
    ServerToolUsage.__init__ = _patched_init

class ClaudetteBrain(Brain):
    "Self-hosted brain using claudette"
    def __init__(self, model='claude-sonnet-4-20250514', sp=None):
        _patch_anthropic()
        from claudette import Chat
        store_attr()
        self.chat = Chat(model, sp=sp or "You are AnyBuddy, a friendly and helpful personal AI assistant. Keep responses concise — this is chat, not an essay.",
                         tools=[dict(type="web_search_20250305", name="web_search")])

    async def send_prompt(self, text):
        r = await asyncio.to_thread(self.chat, text)
        return ''.join(b.text for b in r.content if hasattr(b, 'text'))

    async def ensure_section(self): pass
    async def hide_section(self, header): pass

def get_brain():
    kind = _cli_arg('brain') or os.environ.get('ANYBUDDY_BRAIN', 'solveit')
    if kind == 'claudette': return ClaudetteBrain()
    return SolveitBrain()
