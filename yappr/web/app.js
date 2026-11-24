"use strict";
// Yappr window. Talks to the app through window.pywebview.api.call(method, args) (see yappr/api.py).
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = (m, ...a) => window.pywebview.api.call(m, a);
const HOTKEY = '<span class="kbd">Ctrl</span> + <span class="kbd">Win</span>';
const ICON = {
  said: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/></svg>',
  notes: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h5"/></svg>',
};
const report = (msg) => { try { window.pywebview.api.call("log", [String(msg)]); } catch (e) { /* not connected */ } };
window.addEventListener("error", (e) => report(`${e.message} at ${e.lineno}:${e.colno}`));
window.addEventListener("unhandledrejection", (e) => report(e.reason && (e.reason.stack || e.reason.message) || e.reason));
let S = null; // last state() from the app
let current = "today";
let toastTimer = 0;

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("on"), 2200);
}

function dayLabel(iso) {
  const d = new Date(iso + "T12:00:00");
  const today = new Date(); today.setHours(12, 0, 0, 0);
  const diff = Math.round((today - d) / 86400000);
  if (diff === 0) return "TODAY";
  if (diff === 1) return "YESTERDAY";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }).toUpperCase();
}

function groupByDay(items) {
  const out = [];
  for (const it of items) {
    if (!out.length || out[out.length - 1].date !== it.date) out.push({ date: it.date, items: [] });
    out[out.length - 1].items.push(it);
  }
  return out;
}

async function go(page, arg) {
  current = page;
  document.querySelectorAll(".nav").forEach((n) => n.setAttribute("aria-current", n.dataset.page === page ? "page" : "false"));
  const main = $("#main");
  try {
    await PAGES[page](main, arg);
  } catch (e) {
    main.innerHTML = `<div class="page"><div class="empty"><b>Something went wrong showing this page.</b>${esc(e.message || e)}</div><button class="btn" onclick="go('${page}')">Try again</button></div>`;
  }
  main.focus({ preventScroll: true });
}

// ------------------------------------------------------------------ Today
function setupSteps(st) {
  const prov = st.settings.llm_provider;
  return [
    { done: st.dictated_once, title: "Try a dictation", text: "Hold Ctrl+Win in any text box and talk.", action: ["Show me", () => showWelcome(1)] },
    { done: st.has_key[prov], title: "Add an AI helper", text: "Optional. Smarter clean-up, about a cent a day.", action: ["Set up", () => go("settings", "ai")] },
    { done: st.calendar_connected, title: "Connect your calendar", text: "So Yappr can offer to take notes when a meeting starts.", action: ["Connect", () => go("settings", "meetings")] },
  ];
}

async function pageToday(main) {
  const [t, st] = await Promise.all([api("today"), api("state")]);
  S = st;
  let next;
  if (st.meeting_active) {
    next = `<div class="next"><div class="when" aria-hidden="true">●</div><div class="what"><b>Taking notes now</b>Yappr is recording this call on your PC.</div><button class="btn hi" id="mt">■ Stop notes</button></div>`;
  } else if (t.next_meeting) {
    const n = t.next_meeting;
    next = `<div class="next"><div class="when">${esc(n.start)}</div><div class="what"><b>${esc(n.title)}</b>${n.in_min > 0 ? `Starts in ${n.in_min} min · ` : "Starting now · "}Yappr will offer to take notes</div><button class="btn hi" id="mt">Take notes now</button></div>`;
  } else {
    next = `<div class="next"><div class="what"><b>No meetings coming up</b>${st.calendar_connected ? "Nothing on your calendar for the next few hours." : "Connect your calendar and Yappr will offer to take notes when one starts."}</div><button class="btn hi" id="mt">Take notes now</button></div>`;
  }
  const items = t.timeline.map((e) => e.kind === "said"
    ? `<li><span class="t">${esc(e.time)}</span><span class="k">${ICON.said}Said</span><span>“${esc(e.text)}”</span></li>`
    : `<li><span class="t">${esc(e.time)}</span><span class="k">${ICON.notes}Notes</span><button data-meeting="${esc(e.id)}"><b>${esc(e.text)}</b>${e.minutes ? ` · ${e.minutes} min` : ""}${e.steps ? ` · ${e.steps} next step${e.steps > 1 ? "s" : ""}` : ""}</button></li>`).join("");
  const steps = setupSteps(st);
  const doneN = steps.filter((s) => s.done).length;
  const showSetup = doneN < steps.length && !st.checklist_hidden;
  main.innerHTML = `<div class="page today${showSetup ? " with-setup" : ""}">
    <div>
      <div class="page-head"><h1>Today</h1><span class="muted">${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</span></div>
      ${next}
      <div class="stats" aria-label="Today so far">
        <div><b>${t.words.toLocaleString()}</b><span>words dictated</span></div>
        <div><b>${t.dictations}</b><span>dictation${t.dictations === 1 ? "" : "s"}</span></div>
        <div><b>${t.meetings}</b><span>meeting${t.meetings === 1 ? "" : "s"} noted</span></div>
      </div>
      ${items ? `<ul class="timeline">${items}</ul>` : `<div class="empty"><b>Nothing yet today.</b>Click into any text box, hold ${HOTKEY} and start talking. Let go and your words are typed for you.</div>`}
    </div>
    ${showSetup ? `<aside class="setup" aria-label="Get set up">
      <h3>Get set up · ${doneN} of ${steps.length}</h3>
      <div class="bar"><i style="width:${(doneN / steps.length) * 100}%"></i></div>
      ${steps.map((s, i) => `<div class="chk ${s.done ? "done" : ""}"><span class="b">${s.done ? "✓" : ""}</span><span class="label"><b>${esc(s.title)}${s.done ? " · done" : ""}</b>${s.done ? "" : `<span class="small muted">${esc(s.text)}</span><br><button class="btn" data-step="${i}">${s.action[0]}</button>`}</span></div>`).join("")}
      <button class="link" id="hide-setup">Hide this list</button>
    </aside>` : ""}
  </div>`;
  $("#mt").onclick = async () => { await api("toggle_meeting"); toast(st.meeting_active ? "Stopping notes…" : "Taking notes"); setTimeout(() => current === "today" && go("today"), 1200); };
  main.querySelectorAll("[data-step]").forEach((b) => (b.onclick = steps[b.dataset.step].action[1]));
  main.querySelectorAll("[data-meeting]").forEach((b) => (b.onclick = () => go("notes", { mode: "meetings", id: b.dataset.meeting })));
  const hide = $("#hide-setup");
  if (hide) hide.onclick = async () => { await api("dismiss_checklist"); go("today"); };
}

// ------------------------------------------------------------------ Notes
let notesMode = "meetings";
let notesSel = null;
async function pageNotes(main, arg) {
  if (arg && arg.mode) { notesMode = arg.mode; notesSel = arg.id ?? null; }
  const list = notesMode === "meetings" ? await api("meetings") : await api("dictations");
  if (notesSel === null && list.length) notesSel = notesMode === "meetings" ? list[0].id : list[0].i;
  const groups = groupByDay(list).map((g) => `<div class="day">${dayLabel(g.date)}</div>` + g.items.map((it) => notesMode === "meetings"
    ? `<button class="item" data-id="${esc(it.id)}" aria-current="${it.id === notesSel}"><b>${esc(it.title)}</b><span>${esc(it.time)}${it.minutes ? ` · ${it.minutes} min` : ""}${it.steps ? ` · ${it.steps} next step${it.steps > 1 ? "s" : ""}` : ""}${it.ready ? "" : " · writing notes…"}</span></button>`
    : `<button class="item" data-id="${it.i}" aria-current="${it.i === notesSel}"><b>${esc(it.text || "(empty)")}</b><span>${esc(it.time)}</span></button>`).join("")).join("");
  main.innerHTML = `<div class="notes">
    <div class="list">
      <div class="seg" role="group" aria-label="Show"><button data-mode="meetings" aria-pressed="${notesMode === "meetings"}">Meetings</button><button data-mode="dictations" aria-pressed="${notesMode === "dictations"}">Dictations</button></div>
      ${groups || `<div class="empty small" style="padding:12px">${notesMode === "meetings" ? "No meeting notes yet." : "No dictations yet."}</div>`}
    </div>
    <div class="reader" id="reader"></div>
  </div>`;
  main.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => { notesMode = b.dataset.mode; notesSel = null; go("notes"); }));
  main.querySelectorAll(".item").forEach((b) => (b.onclick = () => {
    notesSel = notesMode === "meetings" ? b.dataset.id : Number(b.dataset.id);
    main.querySelectorAll(".item").forEach((x) => x.setAttribute("aria-current", x === b));
    showNote(list);
  }));
  showNote(list);
}

async function showNote(list) {
  const r = $("#reader");
  if (notesMode === "meetings") {
    if (!list.length) {
      r.innerHTML = `<div class="empty"><b>Your meeting notes will appear here.</b>Click <b>Notes</b> on the bar at the bottom of your screen when a call starts. Yappr records your mic and the call on this PC, then writes a summary with next steps.</div><button class="btn primary" id="startnotes">Take notes now</button>`;
      $("#startnotes").onclick = async () => { await api("toggle_meeting"); toast("Taking notes"); };
      return;
    }
    const m = await api("meeting", notesSel);
    const sec = m.sections.map((s) => {
      const none = s.items.length === 1 && /^none( recorded)?\.?$/i.test(s.items[0].text);
      const body = none ? `<p class="muted">None.</p>`
        : s.heading === "Next steps" ? `<ul class="todo">${s.items.map((i) => `<li><span class="box" aria-label="${i.done ? "done" : "to do"}">${i.done ? "✓" : ""}</span><span>${esc(i.text)}</span></li>`).join("")}</ul>`
        : s.heading ? `<ul>${s.items.map((i) => `<li>${esc(i.text)}</li>`).join("")}</ul>`
        : s.items.map((i) => `<p class="muted">${esc(i.text)}</p>`).join("");
      return (s.heading ? `<h2>${esc(s.heading)}</h2>` : "") + body;
    }).join("");
    r.innerHTML = `<article><div class="meta">${esc(m.when)}</div><h1>${esc(m.title)}</h1>${sec}
      ${m.has_transcript ? `<details class="more" id="tr"><summary>Full transcript</summary><pre>Loading…</pre></details>` : ""}
      <div class="actions"><button class="btn" id="resum">Write the summary again</button><button class="btn" id="openf">Open folder</button></div></article>`;
    const tr = $("#tr");
    if (tr) tr.addEventListener("toggle", async () => { if (tr.open) tr.querySelector("pre").textContent = (await api("transcript", m.id)) || "No transcript."; }, { once: true });
    $("#resum").onclick = async (e) => {
      e.target.disabled = true; e.target.textContent = "Writing…";
      try { await api("resummarize", m.id); toast("Summary updated"); } catch (err) { toast("Couldn't write the summary: " + err.message); }
      go("notes");
    };
    $("#openf").onclick = () => api("open_notes_folder", m.id);
  } else {
    if (!list.length) { r.innerHTML = `<div class="empty"><b>Your dictations will appear here.</b>Hold ${HOTKEY} in any text box and talk.</div>`; return; }
    const d = list.find((x) => x.i === notesSel) || list[0];
    r.innerHTML = `<article><div class="meta">${dayLabel(d.date).toLowerCase().replace(/^./, (c) => c.toUpperCase())} · ${esc(d.time)} · ${d.ai ? "tidied up by your AI helper" : "tidied up on this PC"}${d.pasted ? "" : " · didn't paste (Alt+Shift+Z pastes it again)"}</div>
      <h1>Dictation</h1><div class="said" id="said">${esc(d.text)}</div>
      ${d.raw && d.raw !== d.text ? `<details class="more"><summary>What you actually said</summary><pre>${esc(d.raw)}</pre></details>` : ""}
      <div class="actions"><button class="btn primary" id="copy">Copy text</button></div></article>`;
    $("#copy").onclick = () => { copyText(d.text); toast("Copied"); };
  }
}

function copyText(text) {
  const t = document.createElement("textarea");
  t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
}

// ------------------------------------------------------------------ My words
async function pageWords(main) {
  S = await api("state");
  const render = (entries) => {
    $("#wl").innerHTML = entries.length
      ? entries.map((e) => `<li><span class="w">${esc(e.word)}</span><span class="a">${e.sounds_like.length ? "sounds like “" + e.sounds_like.map(esc).join("”, “") + "”" : ""}</span><button class="btn" data-del="${esc(e.word)}" aria-label="Remove ${esc(e.word)}">Remove</button></li>`).join("")
      : `<li class="empty"><b>No words yet.</b>Add names, brands or jargon Yappr gets wrong, and it will spell them your way.</li>`;
    $("#wl").querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { render(await api("remove_word", b.dataset.del)); toast("Removed"); }));
  };
  main.innerHTML = `<div class="page" style="max-width:860px">
    <div class="page-head"><h1>My words</h1></div>
    <p class="muted" style="max-width:62ch">Names and words Yappr should always spell your way. If it keeps writing something else instead, add that under “Sounds like”.</p>
    <form class="words-add" id="wf">
      <div><label for="ww">Word</label><input class="field" id="ww" placeholder="Kiyosaki" autocomplete="off" required></div>
      <div><label for="wa">Sounds like <span class="muted">(optional, separate with commas)</span></label><input class="field" id="wa" placeholder="key a saki, kiyo saki" autocomplete="off"></div>
      <button class="btn primary" type="submit">Add word</button>
    </form>
    <ul class="wordlist" id="wl"></ul></div>`;
  render(S.dictionary);
  $("#wf").onsubmit = async (e) => {
    e.preventDefault();
    const w = $("#ww").value.trim();
    if (!w) return;
    render(await api("add_word", w, $("#wa").value));
    $("#ww").value = ""; $("#wa").value = ""; $("#ww").focus();
    toast(`Added “${w}”`);
  };
}

// ------------------------------------------------------------------ Settings
function row(title, desc, control, id = "") {
  return `<div class="set"${id ? ` id="${id}"` : ""}><div class="t"><b>${title}</b><span>${desc}</span></div><div class="c">${control}</div><div class="msg"></div></div>`;
}

async function save(changes, el) {
  const res = await api("save_settings", changes);
  const msg = el && el.closest(".set") && el.closest(".set").querySelector(".msg");
  if (!res.ok) {
    if (msg) msg.innerHTML = `<span class="status bad">! ${esc(res.error)}</span>`;
    toast("Not saved");
    return false;
  }
  if (msg) msg.innerHTML = "";
  S.settings = res.settings;
  toast("Saved");
  return true;
}

async function pageSettings(main, section) {
  const [st, mics, usage] = await Promise.all([api("state"), api("microphones"), api("usage")]);
  S = st;
  const s = st.settings;
  const prov = s.llm_provider;
  const claude = prov === "claude";
  const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;
  main.innerHTML = `<div class="page settings">
    <div class="page-head"><h1>Settings</h1></div>
    <nav class="snav" aria-label="Settings sections"><a href="#s-ai">AI helper</a><a href="#s-meetings">Meetings</a><a href="#s-read">Read aloud</a><a href="#s-general">General</a><a href="#s-keys">Shortcuts</a></nav>

    <section class="sgroup" id="s-ai"><h2>AI helper</h2>
      ${row("Tidy up my dictation with AI", "Fixes punctuation, “um”s and repeated words. Only the text is sent to the AI, never your voice. When this is off, Yappr tidies up on this PC with simple rules.", `<input type="checkbox" class="toggle" data-k="use_llm_cleanup" aria-label="Tidy up my dictation with AI"${s.use_llm_cleanup ? " checked" : ""}>`)}
      ${row("Which AI", "Claude is the default: fast, and about a cent a day. Pick the other option to use OpenAI, OpenRouter, Groq, Gemini or one running on this PC.", `<select class="field" id="prov" aria-label="Which AI">${opt("claude", "Claude (Anthropic)", prov)}${opt("openai", "Another AI service (OpenAI-compatible)", prov)}</select>`)}
      ${row("Your key", `${claude ? "Get one at console.anthropic.com → API keys." : "Get one from your AI service's website."} It's kept in Windows Credential Manager, never in a file, and only sent to the service you picked. <b class="status ${st.has_key[prov] ? "ok" : ""}">${st.has_key[prov] ? "✓ Key saved" : "No key yet"}</b>`, `<input class="field" type="password" id="key" placeholder="${st.has_key[prov] ? "•••••••• (saved)" : "Paste your key"}" autocomplete="off" aria-label="Your key"><button class="btn" id="savekey">Save</button>`)}
      ${row("Check it works", "Sends a short test sentence and shows what comes back.", `<button class="btn primary" id="test">Test connection</button>`, "testrow")}
      <details class="adv"><summary>More AI options</summary>
        ${claude ? "" : row("Service address", "The web address from your AI service's instructions, for example https://api.openai.com/v1. It must start with https:// (http:// is only allowed for one running on this PC).", `<input class="field" data-k="llm_base_url" value="${esc(s.llm_base_url)}" aria-label="Service address">`)}
        ${row("Model", "Which version of the AI to use. The default is fast and cheap.", `<input class="field" data-k="llm_model" value="${esc(s.llm_model)}" aria-label="Model">`)}
        ${row("Model for meeting summaries", "Leave blank to use the same model.", `<input class="field" data-k="llm_summary_model" value="${esc(s.llm_summary_model)}" placeholder="Same as above" aria-label="Model for meeting summaries">`)}
        ${row("Prices, for the cost estimate", "US dollars per million tokens sent / received. A token is about ¾ of a word. Only used for the estimate below.", `<input class="field num" type="number" step="0.01" min="0" data-k="price_in_per_m" value="${s.price_in_per_m}" aria-label="Price per million tokens sent"><input class="field num" type="number" step="0.01" min="0" data-k="price_out_per_m" value="${s.price_out_per_m}" aria-label="Price per million tokens received">`)}
        ${row("What it's cost", `Last 30 days: ${usage.calls} request${usage.calls === 1 ? "" : "s"}, $${usage.usd.toFixed(4)}. At this rate, about $${usage.projected_month_usd.toFixed(2)} a month.`, "")}
      </details>
    </section>

    <section class="sgroup" id="s-meetings"><h2>Meetings</h2>
      ${row("Notes folder", "Where meeting notes are saved, as plain files you can open, search and back up. Tip: a folder inside Google Drive backs them up automatically.", `<input class="field" data-k="meetings_dir" value="${esc(s.meetings_dir)}" aria-label="Notes folder"><button class="btn" id="browse">Browse…</button>`)}
      ${row("Calendar link", "Lets Yappr offer to take notes when a meeting starts. In Google Calendar: Settings → your calendar → “Secret address in iCal format”. Yappr only reads it.", `<input class="field" type="password" data-k="calendar_ics_url" value="${esc(s.calendar_ics_url)}" placeholder="Paste the link" aria-label="Calendar link">`)}
      ${row("Ask me", "How many minutes before a meeting starts to offer to take notes.", `<input class="field num" type="number" min="0" step="1" data-k="calendar_prompt_min_before" value="${s.calendar_prompt_min_before}" aria-label="Minutes before a meeting"><span class="muted small">min before</span>`)}
      ${row("Keep notes and dictations for", "Older ones are deleted automatically. At least 1 day.", `<input class="field num" type="number" min="1" step="1" data-k="retention_days" value="${s.retention_days}" aria-label="Days to keep"><span class="muted small">days</span>`)}
    </section>

    <section class="sgroup" id="s-read"><h2>Read aloud</h2>
      <p class="muted" style="margin:-4px 0 12px">Highlight text anywhere and press <span class="kbd">Ctrl</span> + <span class="kbd">Alt</span> + <span class="kbd">X</span>. The voice runs on this PC, so it's free and what you highlight never leaves it.</p>
      ${row("Voice", "", `<select class="field" data-k="read_voice" aria-label="Voice">${Object.entries(st.voices).map(([k, v]) => opt(k, v, s.read_voice)).join("")}</select>`)}
      ${row("Speed", "Also: Ctrl+Alt+] faster, Ctrl+Alt+[ slower.", `<input type="range" class="range" min="0.7" max="2" step="0.1" data-k="read_speed" value="${s.read_speed}" aria-label="Speed"><b id="spd">${Number(s.read_speed).toFixed(1)}×</b>`)}
      ${row("Hear it", "Plays a short sample with the voice and speed above.", `<button class="btn" id="sample">Hear sample</button>`)}
    </section>

    <section class="sgroup" id="s-general"><h2>General</h2>
      ${row("Start Yappr when Windows starts", "", `<input type="checkbox" class="toggle" id="startup" aria-label="Start Yappr when Windows starts"${st.start_with_windows ? " checked" : ""}>`)}
      ${row("Show the bar on screen", "Drag the bar to move it anywhere, or right-click it to hide it. Hotkeys work either way, and you can always open Yappr from the tray icon by the clock.", `<input type="checkbox" class="toggle" data-k="show_bar" aria-label="Show the bar"${s.show_bar ? " checked" : ""}>`)}
      ${st.bar_moved ? row("Bar position", "You moved the bar. Put it back at the bottom centre of the screen?", `<button class="btn" id="barreset">Move it back</button>`) : ""}
      ${row("Microphone", "", `<select class="field" data-k="mic_device" aria-label="Microphone">${opt("", "Windows default", s.mic_device)}${mics.map((m) => opt(m, m.replace(/, MME$/, ""), s.mic_device)).join("")}</select>`)}
      ${row("Free up memory after", "Yappr unloads its speech engine when you haven't dictated for a while; the next dictation then takes a second longer. 0 keeps it ready.", `<input class="field num" type="number" min="0" step="1" data-k="stt_idle_unload_min" value="${s.stt_idle_unload_min}" aria-label="Minutes idle"><span class="muted small">min idle</span>`)}
    </section>

    <section class="sgroup" id="s-keys"><h2>Shortcuts</h2>
      <div class="keys">
        <span>${HOTKEY} <span class="muted small">(hold)</span></span><span>Talk while held. Let go to paste.</span>
        <span>${HOTKEY}, then <span class="kbd">Space</span></span><span>Hands-free: keeps listening. ${HOTKEY} again to stop.</span>
        <span><span class="kbd">Alt</span> + <span class="kbd">Shift</span> + <span class="kbd">Z</span></span><span>Paste the last dictation again.</span>
        <span><span class="kbd">Ctrl</span> + <span class="kbd">Alt</span> + <span class="kbd">X</span></span><span>Read the highlighted text aloud (again to stop). <span class="kbd">P</span> instead of X pauses.</span>
      </div>
      <p style="margin-top:16px"><button class="link" id="rewelcome">Show the welcome again</button></p>
    </section>
  </div>`;

  // auto-save every [data-k] control
  main.querySelectorAll("[data-k]").forEach((el) => {
    const ev = el.type === "checkbox" || el.tagName === "SELECT" || el.type === "range" ? "change" : "change";
    el.addEventListener(ev, () => {
      const v = el.type === "checkbox" ? el.checked : el.type === "number" || el.type === "range" ? Number(el.value) : el.value;
      save({ [el.dataset.k]: v }, el);
    });
  });
  const spd = main.querySelector('[data-k="read_speed"]');
  spd.addEventListener("input", () => ($("#spd").textContent = Number(spd.value).toFixed(1) + "×"));
  $("#prov").onchange = async (e) => {
    const np = e.target.value;
    const [m, pin, pout] = st.provider_defaults[np];
    const changes = { llm_provider: np };
    const oldDefault = st.provider_defaults[prov][0];
    if (!s.llm_model || s.llm_model === oldDefault) Object.assign(changes, { llm_model: m, price_in_per_m: pin, price_out_per_m: pout });
    if (await save(changes, e.target)) go("settings", "ai");
  };
  $("#savekey").onclick = async (e) => {
    const k = $("#key").value.trim();
    if (!k) { toast("Paste your key first"); return; }
    await api("set_api_key", prov, k);
    toast("Key saved");
    go("settings", "ai");
  };
  $("#test").onclick = async (e) => {
    const msg = $("#testrow .msg");
    e.target.disabled = true;
    msg.innerHTML = `<span class="status">Testing…</span>`;
    const r = await api("test_connection", prov, S.settings.llm_base_url, S.settings.llm_model, $("#key").value);
    msg.innerHTML = r.ok ? `<span class="status ok">✓ ${esc(r.message)}</span> <span class="small muted">It tidied the test to: “${esc(r.sample)}”</span>` : `<span class="status bad">! ${esc(r.message)}</span>`;
    e.target.disabled = false;
  };
  $("#browse").onclick = async () => {
    const d = await window.pywebview.api.browse_folder();
    if (d) { const el = main.querySelector('[data-k="meetings_dir"]'); el.value = d; save({ meetings_dir: d }, el); }
  };
  $("#sample").onclick = () => api("hear_sample", main.querySelector('[data-k="read_voice"]').value, Number(spd.value));
  $("#startup").onchange = async (e) => { await api("set_start_with_windows", e.target.checked); toast(e.target.checked ? "Yappr will start with Windows" : "Yappr won't start with Windows"); };
  const br = $("#barreset");
  if (br) br.onclick = async () => { await api("reset_bar_position"); toast("Bar moved back"); go("settings", "general"); };
  $("#rewelcome").onclick = () => showWelcome(1);
  if (section) { const el = $("#s-" + section); if (el) el.scrollIntoView(); }
}

// ------------------------------------------------------------------ Welcome (first run)
let pollTimer = 0;
async function showWelcome(step = 1) {
  const w = $("#welcome");
  w.hidden = false;
  clearInterval(pollTimer);
  S = await api("state");
  const steps = (n) => `<div class="steps" aria-label="Step ${n} of 3">${[1, 2, 3].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</div><div class="small muted">Step ${n} of 3</div>`;
  if (step === 1) {
    const before = await api("last_dictation");
    w.innerHTML = `<div class="wcard">
      <img src="${window.SKIP}" alt="" width="64" height="64" style="border-radius:16px">
      ${steps(1)}
      <h1>Hi, I'm Yappr. Let's try it.</h1>
      <p>Click in the box below, then <b>hold</b> ${HOTKEY} and say something, like what you had for breakfast. Let go, and your words are typed for you.</p>
      <textarea class="field try" id="try" placeholder="Your words will appear here…" aria-label="Practice box"></textarea>
      <div id="got" role="status" aria-live="polite"></div>
      <div class="wfoot"><button class="link" id="skip1">Skip this</button><button class="btn primary" id="next1" disabled>Next</button></div></div>`;
    $("#try").focus();
    const seen = before ? before.ts : "";
    pollTimer = setInterval(async () => {
      const d = await api("last_dictation");
      if (d && d.ts !== seen) {
        clearInterval(pollTimer);
        $("#got").innerHTML = `<div class="got">✓ That's it. Works in any app: email, chat, documents.</div>`;
        $("#next1").disabled = false;
        $("#next1").focus();
      }
    }, 700);
    $("#next1").onclick = () => showWelcome(2);
    $("#skip1").onclick = () => showWelcome(2);
  } else if (step === 2) {
    const prov = S.settings.llm_provider;
    w.innerHTML = `<div class="wcard">
      ${steps(2)}
      <h1>Want smarter clean-up?</h1>
      <p>Yappr already fixes the basics on this PC. With an AI helper it also fixes punctuation, “um”s and rambling. Only the text is sent, never your voice, and it costs about a cent a day. You can skip this and add it later in Settings.</p>
      <div style="margin-top:18px">
        ${row("Which AI", "Claude is the default.", `<select class="field" id="wprov" aria-label="Which AI"><option value="claude"${prov === "claude" ? " selected" : ""}>Claude (Anthropic)</option><option value="openai"${prov === "openai" ? " selected" : ""}>Another AI service</option></select>`)}
        ${prov === "openai" ? row("Service address", "The web address from your AI service's instructions, for example https://api.openai.com/v1.", `<input class="field" id="wurl" value="${esc(S.settings.llm_base_url)}" aria-label="Service address">`, "wurlrow") : ""}
        ${row("Your key", `${prov === "claude" ? "From console.anthropic.com → API keys." : "From your AI service's website."} Kept in Windows Credential Manager, never in a file.`, `<input class="field" type="password" id="wkey" placeholder="${S.has_key[prov] ? "•••••••• (saved)" : "Paste your key"}" aria-label="Your key">`, "wkeyrow")}
      </div>
      <div class="wfoot"><button class="link" id="skip2">Skip for now</button><button class="btn primary" id="next2">${S.has_key[prov] ? "Next" : "Check and save"}</button></div></div>`;
    $("#wprov").onchange = async (e) => {
      const np = e.target.value;
      const [m, pin, pout] = S.provider_defaults[np];
      await api("save_settings", { llm_provider: np, llm_model: m, price_in_per_m: pin, price_out_per_m: pout });
      showWelcome(2);
    };
    $("#skip2").onclick = () => showWelcome(3);
    $("#next2").onclick = async (e) => {
      const k = $("#wkey").value.trim();
      const msg = $("#wkeyrow .msg");
      if (!k) { if (S.has_key[prov]) return showWelcome(3); msg.innerHTML = `<span class="status bad">! Paste your key first, or skip for now.</span>`; return; }
      e.target.disabled = true;
      msg.innerHTML = `<span class="status">Checking…</span>`;
      let url = S.settings.llm_base_url;
      if (prov === "openai") {
        url = $("#wurl").value.trim();
        const saved = await api("save_settings", { llm_base_url: url });
        if (!saved.ok) { $("#wurlrow .msg").innerHTML = `<span class="status bad">! ${esc(saved.error)}</span>`; msg.innerHTML = ""; e.target.disabled = false; return; }
      }
      const r = await api("test_connection", prov, url, S.settings.llm_model, k);
      if (r.ok) { await api("set_api_key", prov, k); msg.innerHTML = `<span class="status ok">✓ ${esc(r.message)}. Key saved.</span>`; setTimeout(() => showWelcome(3), 900); }
      else { msg.innerHTML = `<span class="status bad">! ${esc(r.message)}</span>`; e.target.disabled = false; }
    };
  } else {
    w.innerHTML = `<div class="wcard">
      ${steps(3)}
      <h1>Meeting notes, when you want them</h1>
      <p>Click <b>Notes</b> on the bar at the bottom of your screen when a call starts. Yappr records your mic and the call on this PC, and writes a summary with next steps when it ends.</p>
      <div style="margin-top:18px">${row("Calendar link (optional)", "Yappr can offer to take notes when a meeting starts. In Google Calendar: Settings → your calendar → “Secret address in iCal format”.", `<input class="field" type="password" id="wcal" placeholder="Paste the link" aria-label="Calendar link">`, "wcalrow")}</div>
      <div class="wfoot"><span class="small muted">Highlight any text and press Ctrl+Alt+X to hear it read aloud.</span><button class="btn primary" id="done">Start using Yappr</button></div></div>`;
    $("#done").onclick = async () => {
      const cal = $("#wcal").value.trim();
      if (cal) await api("save_settings", { calendar_ics_url: cal });
      await api("finish_onboarding");
      hideWelcome();
      go("today");
    };
  }
}

function hideWelcome() {
  clearInterval(pollTimer);
  $("#welcome").hidden = true;
  $("#welcome").innerHTML = "";
}

const PAGES = { today: pageToday, notes: pageNotes, words: pageWords, settings: pageSettings };

async function start() {
  document.querySelectorAll(".nav").forEach((n) => (n.onclick = () => go(n.dataset.page)));
  const page = document.body.dataset.start;
  S = await api("state");
  if (page === "welcome" || !S.onboarded) { await go("today"); showWelcome(1); }
  else go(PAGES[page] ? page : "today");
}

if (window.pywebview && window.pywebview.api && window.pywebview.api.call) start(); // methods ready already
else window.addEventListener("pywebviewready", start);
