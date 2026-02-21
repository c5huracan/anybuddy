import os, re, asyncio
import datetime as dt
from zoneinfo import ZoneInfo
from fastcore.utils import store_attr
from dialoghelper import find_msgs, add_msg, add_prompt, update_msg, dh_settings

DNAME = os.environ.get('ANYBUDDY_DIALOG', 'anybuddy-discord')
TZ = os.environ.get('ANYBUDDY_TZ', 'US/Central')
VERBOSE = os.environ.get('ANYBUDDY_VERBOSE', '').lower() in ('1', 'true')

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
