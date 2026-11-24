"""Screenshot every page of the Yappr window with example data, in light and dark, at real window size.

    .venv\\Scripts\\python.exe tools\\ui_preview.py [out_dir]

Builds the same inlined page the app shows (yappr.window.build_html) but swaps the app connection for a
mock with clearly fake example data, then renders it with headless Edge. Nothing here runs the app.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yappr.window import build_html  # noqa: E402

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

SUMMARY = {
    "id": "2026-11-24 1000 Q4 planning", "title": "Q4 planning", "when": "Tuesday, November 24, 2026 at 10:00",
    "has_transcript": True, "with": "Sam Ortiz, Priya Nair", "calendar": "https://www.google.com/calendar/event?eid=example",
    "sections": [
        {"heading": "Summary", "items": [{"text": "The team agreed to ship the beta on 12 December and hold pricing until January."},
                                         {"text": "Design needs two more weeks for onboarding screens."},
                                         {"text": "Support wants a short FAQ before invites go out."}]},
        {"heading": "Decisions", "items": [{"text": "Beta ships 12 December."}, {"text": "No price change before January."}]},
        {"heading": "Next steps", "items": [{"text": "Sam — send the beta invite list (by Friday)", "done": False},
                                            {"text": "Priya — draft the onboarding screens", "done": False},
                                            {"text": "Me — confirm the launch date with legal", "done": True}]},
        {"heading": "Open questions", "items": [{"text": "None"}]},
        {"heading": "Key moments", "items": [{"text": "[0:03:10] Launch date proposed"}, {"text": "[0:21:45] Pricing discussion"}]},
    ],
}

SCENARIOS = {
    "new": dict(onboarded=False, dictated=False, key=False, cal=False, timeline=False, next=False),
    "setup": dict(onboarded=True, dictated=True, key=False, cal=False, timeline=True, next=False),
    "full": dict(onboarded=True, dictated=True, key=True, cal=True, timeline=True, next=True),
    "empty": dict(onboarded=True, dictated=True, key=True, cal=True, timeline=False, next=False),
    "google": dict(onboarded=True, dictated=True, key=True, cal=False, gconn=True, timeline=True, next=True),
}


def mock_js(sc: dict, welcome_step: int = 0, section: str = "") -> str:
    return """
(function(){
const SC = %s;
const today = new Date().toISOString().slice(0,10);
const yest = new Date(Date.now()-86400000).toISOString().slice(0,10);
const st = {
  settings: {llm_provider:"claude", llm_base_url:"https://api.openai.com/v1", llm_model:"claude-haiku-5-5", llm_summary_model:"",
    price_in_per_m:0.1, price_out_per_m:0.5, use_llm_cleanup:true, stt_idle_unload_min:10, mic_device:"",
    meetings_dir:"C:\\\\Users\\\\you\\\\Documents\\\\Yappr\\\\Meetings", retention_days:90, calendar_ics_url: SC.cal ? "https://calendar.example/secret.ics" : "",
    calendar_prompt_min_before:1, read_voice:"af_heart", read_speed:1.3, show_bar:true},
  provider_defaults: {claude:["claude-haiku-5-5",0.1,0.5], openai:["gpt-4.1-nano",0.1,0.4]},
  providers: {claude:"Claude (Anthropic)", openai:"OpenAI-compatible"},
  has_key: {claude: SC.key, openai:false},
  voices: {af_heart:"Heart (US, female)", am_michael:"Michael (US, male)", bf_emma:"Emma (UK, female)"},
  start_with_windows: true, onboarded: SC.onboarded, checklist_hidden:false, dictated_once: SC.dictated,
  calendar_connected: SC.cal || !!SC.gconn, meeting_active:false,
  google: {available:true, connected: !!SC.gconn, email: SC.gconn ? "you@example.com" : "", busy:false, error:""},
  dictionary: [{word:"Kiyosaki", sounds_like:["key a saki"]},{word:"Northwind", sounds_like:[]},{word:"Priya", sounds_like:["preeya"]}],
};
const tl = SC.timeline ? [
  {kind:"said", time:"11:42", text:"Thanks for the quick turnaround, let's lock it for Friday."},
  {kind:"notes", time:"10:00", text:"Q4 planning", id:"2026-11-24 1000 Q4 planning", steps:3, minutes:47},
  {kind:"said", time:"09:15", text:"Can you send me the deck before standup?"}] : [];
const M = {
  state: () => st,
  today: () => ({words: SC.timeline ? 1284 : 0, dictations: SC.timeline ? 14 : 0, meetings: SC.timeline ? 1 : 0, timeline: tl,
                 next_meeting: SC.next ? {title:"Design sync", start:"14:00", in_min:18} : null}),
  meetings: () => SC.timeline ? [
    {id:"2026-11-24 1000 Q4 planning", title:"Q4 planning", date:today, time:"10:00", steps:3, minutes:47, ready:true},
    {id:"b", title:"Hiring sync", date:yest, time:"15:30", steps:1, minutes:22, ready:true},
    {id:"c", title:"Client call: Northwind", date:yest, time:"11:00", steps:4, minutes:58, ready:true}] : [],
  meeting: () => (%s),
  transcript: () => "[0:00:02] Me: Okay, let's get started.\\n[0:00:06] Others: Morning everyone.",
  dictations: () => [
    {i:0, date:today, time:"11:42", text:"Thanks for the quick turnaround, let's lock it for Friday.", raw:"thanks for the uh quick turnaround lets lock it for friday", ai:true, pasted:true},
    {i:1, date:today, time:"09:15", text:"Can you send me the deck before standup?", raw:"can you send me the deck before standup", ai:true, pasted:true}],
  microphones: () => ["Microphone (USB Audio), MME", "Headset (Jabra), MME"],
  usage: () => ({calls: 212, usd: 0.0431, projected_month_usd: 0.06}),
  last_dictation: () => null,
  google_status: () => st.google,
};
window.pywebview = {api: {call: async (m, a) => (M[m] ? M[m](...(a||[])) : true), browse_folder: async () => null}};
window.__WELCOME = %d; window.__SECTION = %s;
})();
""" % (json.dumps(sc), json.dumps(SUMMARY), welcome_step, json.dumps(section))


SHOTS = [  # name, start page, scenario, welcome step, settings section, height
    ("welcome-1", "today", "new", 1, "", 700),
    ("welcome-2", "today", "new", 2, "", 700),
    ("welcome-3", "today", "new", 3, "", 700),
    ("today-new", "today", "setup", 0, "", 700),
    ("today", "today", "full", 0, "", 700),
    ("notes-meeting", "notes", "full", 0, "", 760),
    ("notes-dictation", "notes", "full", 0, "dictations", 700),
    ("notes-empty", "notes", "empty", 0, "", 700),
    ("words", "words", "full", 0, "", 700),
    ("settings", "settings", "setup", 0, "", 2600),
    ("settings-google", "settings", "google", 0, "", 2600),
]


def page_for(start: str, sc: str, step: int, section: str, dark: bool) -> str:
    html = build_html(start)
    html = html.replace('<script>window.SKIP', f"<script>{mock_js(SCENARIOS[sc], step, section)}</script>\n<script>window.SKIP", 1)
    # drive the page into the wanted state once it has started
    driver = """<script>window.addEventListener('load',()=>setTimeout(async()=>{
      if (window.__WELCOME) { await showWelcome(window.__WELCOME); }
      else if (window.__SECTION==='dictations') { await go('notes',{mode:'dictations',id:0}); }
    },300));</script></body>"""
    html = html.replace("</body>", driver)
    if dark:
        html = html.replace("@media (prefers-color-scheme: dark)", "@media all")
        html = html.replace('<meta name="color-scheme" content="light dark">', '<meta name="color-scheme" content="dark">')
    return html


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "loop-ui" / "shots"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, start, sc, step, section, h in SHOTS:
            for theme in ("light", "dark"):
                f = Path(tmp) / f"{name}-{theme}.html"
                f.write_text(page_for(start, sc, step, section, theme == "dark"), encoding="utf-8")
                png = out / f"{name}-{theme}.png"
                subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=3000",
                                f"--window-size=1040,{h}", f"--screenshot={png}", f.as_uri()],
                               check=True, capture_output=True, timeout=60)
                print(png)


if __name__ == "__main__":
    main()
