#!/usr/bin/env python3
"""Build the term dashboard from courses.yml + tasks.yml.

Usage:
    python3 study/build_dashboard.py            # writes study/dashboard.html
    python3 study/build_dashboard.py --brief    # prints the plain-text daily brief

The page renders its hero, calendar and task list in the browser from a baked
JSON payload, so completing and adding activities can update the view live.
Those edits live in the viewer's own device storage; courses.yml / tasks.yml
stay the source of truth and are reconciled from the page's export file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required:  pip install pyyaml")

HERE = Path(__file__).resolve().parent

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS = DAY_KEYS[:5]
DAY_PT = {"mon": "SEG", "tue": "TER", "wed": "QUA", "thu": "QUI", "fri": "SEX", "sat": "SÁB", "sun": "DOM"}
MONTH_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
FULLDAY_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
FULLMONTH_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                "agosto", "setembro", "outubro", "novembro", "dezembro"]
TYPE_PT = {
    "assignment": "Trabalho", "exam": "Prova", "reading": "Leitura",
    "paper": "Artigo", "presentation": "Seminário", "admin": "Pendência",
}

TIMETABLE_START = 8 * 60
TIMETABLE_END = 21 * 60


# --------------------------------------------------------------------------
# loading + helpers
# --------------------------------------------------------------------------

def load() -> tuple[dict, dict]:
    courses = yaml.safe_load((HERE / "courses.yml").read_text(encoding="utf-8")) or {}
    tasks = yaml.safe_load((HERE / "tasks.yml").read_text(encoding="utf-8")) or {}
    return courses, tasks


def today_in(tzname: str) -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tzname)).date()
    except Exception:
        return (dt.datetime.utcnow() - dt.timedelta(hours=3)).date()


def minutes(hhmm) -> int:
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def as_date(value) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def br_date(d: dt.date) -> str:
    return f"{DAY_PT[DAY_KEYS[d.weekday()]].lower()} {d.day} {MONTH_PT[d.month - 1]}"


def countdown(days: int | None) -> str:
    if days is None:
        return "sem data"
    if days < 0:
        return f"{abs(days)}d atrasado"
    if days == 0:
        return "hoje"
    if days == 1:
        return "amanhã"
    return f"{days} dias"


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def assign_lanes(items: list[dict]) -> tuple[list[tuple[dict, int]], int]:
    """Place same-day classes into side-by-side lanes so an overlap is visible
    rather than one block hiding behind another."""
    lane_ends: list[int] = []
    placed: list[tuple[dict, int]] = []
    for item in items:
        start = minutes(item["slot"].get("start"))
        end = minutes(item["slot"].get("end"))
        for i, lane_end in enumerate(lane_ends):
            if start >= lane_end:
                lane_ends[i] = end
                placed.append((item, i))
                break
        else:
            lane_ends.append(end)
            placed.append((item, len(lane_ends) - 1))
    return placed, max(len(lane_ends), 1)


def build_model(courses_doc: dict, tasks_doc: dict) -> dict:
    tz = courses_doc.get("timezone") or "America/Sao_Paulo"
    today = today_in(tz)
    courses = courses_doc.get("courses") or []
    by_id = {c.get("id"): c for c in courses}
    cap = courses_doc.get("study_capacity") or {}
    capacity = {k: (cap.get(k) or 0) for k in DAY_KEYS}

    tasks = []
    for raw in (tasks_doc.get("tasks") or []):
        due = as_date(raw.get("due"))
        course = by_id.get(raw.get("course")) or {}
        tasks.append({
            "id": raw.get("id"),
            "title": raw.get("title") or "(sem título)",
            "type": (raw.get("type") or "assignment").lower(),
            "course": raw.get("course") or "none",
            "course_name": course.get("name", "Sem disciplina"),
            "due": due.isoformat() if due else None,
            "due_time": raw.get("due_time") or "",
            "effort": raw.get("effort") or 0,
            "status": (raw.get("status") or "todo").lower(),
            "notes": " ".join((raw.get("notes") or "").split()),
        })

    week: dict[str, list[dict]] = {k: [] for k in DAY_KEYS}
    for c in courses:
        for slot in (c.get("schedule") or []):
            key = (slot.get("day") or "").lower()
            if key in week:
                week[key].append({"course": c, "slot": slot})
    for key in week:
        week[key].sort(key=lambda x: minutes(x["slot"].get("start")))

    clashes = {}
    for key in DAY_KEYS:
        items = week[key]
        pairs = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i]["slot"], items[j]["slot"]
                if minutes(a.get("start")) < minutes(b.get("end")) and \
                   minutes(b.get("start")) < minutes(a.get("end")):
                    pairs.append((items[i]["course"].get("name", ""), items[j]["course"].get("name", "")))
        if pairs:
            clashes[key] = pairs

    return {
        "today": today, "tz": tz, "term": courses_doc.get("term") or "",
        "courses": courses, "tasks": tasks, "capacity": capacity,
        "week": week, "clashes": clashes,
    }


def open_tasks(m: dict) -> list[dict]:
    today = m["today"]
    out = []
    for t in m["tasks"]:
        if t["status"] == "done":
            continue
        d = as_date(t["due"])
        out.append({**t, "days": (d - today).days if d else None})
    out.sort(key=lambda t: (t["days"] is None, t["days"] if t["days"] is not None else 0))
    return out


def available_hours(m: dict, start: dt.date, ndays: int) -> int:
    return sum(m["capacity"][DAY_KEYS[(start + dt.timedelta(days=i)).weekday()]]
               for i in range(ndays))


# --------------------------------------------------------------------------
# plain-text brief (used by the scheduled morning push)
# --------------------------------------------------------------------------

def brief(m: dict) -> str:
    today = m["today"]
    opens = open_tasks(m)
    late = [t for t in opens if t["days"] is not None and t["days"] < 0]
    next7 = [t for t in opens if t["days"] is not None and 0 <= t["days"] <= 7]
    next14 = [t for t in opens if t["days"] is not None and 0 <= t["days"] <= 14]
    h7 = sum(t["effort"] for t in next7)
    h14 = sum(t["effort"] for t in next14)

    lines = [f"{FULLDAY_PT[today.weekday()]}, {today.day} de {FULLMONTH_PT[today.month - 1]}"]

    if late:
        lines += ["", f"ATRASADO ({len(late)}):"]
        lines += [f"  - {t['title']} [{t['course_name']}] {countdown(t['days'])}" for t in late]

    todays = m["week"][DAY_KEYS[today.weekday()]]
    if todays:
        lines += ["", "Aulas hoje:"]
        for item in todays:
            s = item["slot"]
            where = f" ({s.get('where')})" if s.get("where") else ""
            lines.append(f"  - {s.get('start','')}-{s.get('end','')} {item['course']['name']}{where}")
    else:
        lines += ["", "Sem aulas hoje."]

    if next7:
        lines += ["", f"Nos próximos 7 dias ({h7}h de trabalho):"]
        lines += [f"  - {countdown(t['days']):>12}  {t['title']} [{t['course_name']}]" for t in next7]
    else:
        lines += ["", "Nada nos próximos 7 dias."]

    # The 7-day figure hides a big deliverable sitting on day 8-14, which is
    # exactly when it is still cheap to start.
    if h14 > h7:
        lines += ["", f"Próximos 14 dias: {h14}h em {len(next14)} item(ns)."]

    avail = available_hours(m, today, 14)
    if h14 > avail:
        lines += ["", f"ATENÇÃO: {h14}h de trabalho contra {avail}h disponíveis nos próximos 14 dias."]

    return "\n".join(lines)


# --------------------------------------------------------------------------
# stylesheet
# --------------------------------------------------------------------------

CSS = """
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: light;
  --bg:     #F5F6F8;
  --card:   #FFFFFF;
  --sunken: #EBEDF1;
  --ink:    #16181D;
  --muted:  #5C6371;
  --faint:  #8B92A0;
  --line:   #E4E7EC;
  --hair:   #EFF1F4;

  --danger: #A93226;
  --danger-soft: #FBEAE7;
  --warn:   #8A6100;
  --warn-soft: #FBF2DD;
  --ok:     #1D6B4C;
  --ok-soft: #E6F2EB;

  --shadow: 0 1px 2px rgba(22,24,29,.04), 0 4px 14px -8px rgba(22,24,29,.10);
  --r: 14px;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg:     #121417;
    --card:   #1A1D22;
    --sunken: #23272E;
    --ink:    #E9EBEF;
    --muted:  #9BA3B1;
    --faint:  #6E7684;
    --line:   #282D35;
    --hair:   #222730;

    --danger: #F09A8C;
    --danger-soft: #33201D;
    --warn:   #E5BC72;
    --warn-soft: #2E2612;
    --ok:     #74CFA4;
    --ok-soft: #16291F;

    --shadow: 0 1px 2px rgba(0,0,0,.35), 0 6px 18px -10px rgba(0,0,0,.5);
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg:     #121417;
  --card:   #1A1D22;
  --sunken: #23272E;
  --ink:    #E9EBEF;
  --muted:  #9BA3B1;
  --faint:  #6E7684;
  --line:   #282D35;
  --hair:   #222730;

  --danger: #F09A8C;
  --danger-soft: #33201D;
  --warn:   #E5BC72;
  --warn-soft: #2E2612;
  --ok:     #74CFA4;
  --ok-soft: #16291F;

  --shadow: 0 1px 2px rgba(0,0,0,.35), 0 6px 18px -10px rgba(0,0,0,.5);
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -webkit-text-size-adjust: 100%;
}
.page { max-width: 720px; margin: 0 auto; padding: 22px 16px 80px; display: flex; flex-direction: column; gap: 28px; }
.term { font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--faint); }
h1 { font-size: clamp(21px,5.4vw,27px); font-weight: 650; letter-spacing: -.02em; margin: 2px 0 0; text-wrap: balance; }
h2 { font-size: 12.5px; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; color: var(--faint); margin: 0 0 11px; }
.sec-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 11px; }
.sec-head h2 { margin: 0; }

/* ---------- hero ---------- */
.hero { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 19px;
        display: flex; flex-direction: column; gap: 15px; border-top: 3px solid var(--c, var(--line)); }
.hero-label { font-size: 11.5px; font-weight: 650; letter-spacing: .09em; text-transform: uppercase; color: var(--c, var(--muted)); }
.hero-main { display: flex; gap: 17px; align-items: center; }
.hero-num { font-family: var(--mono); font-size: clamp(40px,12vw,56px); font-weight: 600; line-height: .9;
            letter-spacing: -.04em; font-variant-numeric: tabular-nums; color: var(--c, var(--ink)); }
.hero-unit { display: block; font-family: var(--sans); font-size: 11.5px; font-weight: 600;
             letter-spacing: .09em; text-transform: uppercase; color: var(--faint); margin-top: 6px; }
.hero-title { font-size: 17px; font-weight: 600; line-height: 1.3; text-wrap: pretty; }
.hero-meta { font-size: 13.5px; color: var(--muted); margin-top: 4px; }

.gauge { display: flex; flex-direction: column; gap: 7px; }
.gauge-row { display: flex; justify-content: space-between; align-items: baseline; font-size: 13px; }
.gauge-lab { color: var(--muted); }
.gauge-val { font-family: var(--mono); font-weight: 600; font-variant-numeric: tabular-nums; }
.gauge-track { height: 8px; border-radius: 5px; background: var(--sunken); overflow: hidden; display: flex; }
.gauge-fill { background: var(--ok); }
.gauge-over { background: var(--danger); }

.note-box { display: flex; gap: 9px; align-items: flex-start; border-radius: 10px; padding: 11px 13px; font-size: 13.5px; font-weight: 500; }
.note-box.bad { background: var(--danger-soft); color: var(--danger); }
.note-box.warn { background: var(--warn-soft); color: var(--warn); }
.note-box svg { flex: none; margin-top: 2px; }

/* ---------- calendar ---------- */
.cal { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 15px 13px 13px; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.cal-dow { font-size: 9.5px; font-weight: 700; letter-spacing: .06em; color: var(--faint); text-align: center; padding-bottom: 5px; }
.cal-cell {
  position: relative; aspect-ratio: 1 / 1; min-height: 40px;
  border: 0; background: transparent; border-radius: 9px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
  font: inherit; font-size: 13px; color: var(--ink); cursor: pointer; padding: 2px;
}
.cal-cell.past { opacity: .4; }
.cal-cell .mlab { font-size: 8px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--faint); line-height: 1; }
.cal-cell.has { background: var(--sunken); }
.cal-cell.today { box-shadow: inset 0 0 0 2px var(--ink); font-weight: 700; }
.cal-cell[aria-pressed="true"] { background: var(--ink); color: var(--bg); }
.cal-cell:focus-visible { outline: 2px solid var(--ink); outline-offset: 1px; }
.cal-cell .n { font-variant-numeric: tabular-nums; line-height: 1; }
.cal-dots { display: flex; gap: 2px; height: 5px; align-items: center; }
.cal-dots i { width: 5px; height: 5px; border-radius: 50%; background: var(--dc); display: block; }
.cal-cell.nostudy .n { text-decoration: underline dotted; text-underline-offset: 3px; }
.cal-legend { font-size: 11px; color: var(--faint); margin-top: 11px; line-height: 1.6; }

/* ---------- filters + list ---------- */
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 11px; }
.chip { font: inherit; font-size: 12.5px; font-weight: 550; color: var(--muted); background: var(--card);
        border: 1px solid var(--line); border-radius: 999px; padding: 7px 13px; cursor: pointer; min-height: 34px; }
.chip[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--bg); }
.chip:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.chip.clear { color: var(--danger); border-color: var(--danger); background: transparent; }

.list { display: flex; flex-direction: column; gap: 7px; }
.item { background: var(--card); border-radius: 12px; box-shadow: var(--shadow); overflow: hidden;
        border-left: 3px solid var(--c, var(--line)); }
.it-row { display: flex; gap: 11px; align-items: center; padding: 12px 13px; }
.box { flex: none; width: 24px; height: 24px; border-radius: 7px; border: 1.8px solid var(--line);
       background: var(--card); cursor: pointer; display: grid; place-items: center; padding: 0; color: transparent; }
.box:hover { border-color: var(--muted); }
.box:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.item.done .box { background: var(--ok); border-color: var(--ok); color: var(--card); }
.it-main { flex: 1; min-width: 0; cursor: pointer; }
.it-title { font-size: 14.5px; font-weight: 550; line-height: 1.35; text-wrap: pretty; }
.it-sub { font-size: 12px; color: var(--faint); margin-top: 2px; }
.pill { flex: none; font-family: var(--mono); font-size: 10.5px; font-weight: 600; padding: 5px 8px;
        border-radius: 999px; background: var(--sunken); color: var(--muted); white-space: nowrap;
        font-variant-numeric: tabular-nums; }
.item.late .pill, .item.now .pill { background: var(--danger-soft); color: var(--danger); }
.item.soon .pill { background: var(--warn-soft); color: var(--warn); }
.item.done { opacity: .5; }
.item.done .it-title { text-decoration: line-through; }
.item.done .pill { background: var(--ok-soft); color: var(--ok); }
.it-note { font-size: 13.5px; color: var(--muted); padding: 11px 13px 13px; margin: 0;
           border-top: 1px solid var(--hair); line-height: 1.55; display: none; }
.item.open .it-note { display: block; }
.it-del { font: inherit; font-size: 12px; background: none; border: 0; color: var(--danger);
          cursor: pointer; padding: 4px 6px; border-radius: 6px; }
.badge-mine { font-size: 9.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
              color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 1px 4px; margin-left: 6px; }
.empty { font-size: 13.5px; color: var(--faint); padding: 16px 2px; }

/* ---------- add form ---------- */
.add-btn { font: inherit; font-size: 14px; font-weight: 600; width: 100%; padding: 13px;
           border-radius: 12px; border: 1.5px dashed var(--line); background: var(--card);
           color: var(--muted); cursor: pointer; margin-top: 8px; }
.add-btn:hover { border-color: var(--muted); color: var(--ink); }
.add-btn:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.form { background: var(--card); border-radius: 12px; box-shadow: var(--shadow); padding: 15px;
        margin-top: 8px; display: none; flex-direction: column; gap: 11px; }
.form.open { display: flex; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 11.5px; font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--faint); }
.field input, .field select {
  font: inherit; font-size: 15px; padding: 10px 11px; border-radius: 9px;
  border: 1px solid var(--line); background: var(--bg); color: var(--ink); min-height: 44px; width: 100%;
}
.field input:focus, .field select:focus { outline: 2px solid var(--ink); outline-offset: -1px; }
.form-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 11px; }
.form-actions { display: flex; gap: 8px; margin-top: 3px; }
.btn { font: inherit; font-size: 14px; font-weight: 600; padding: 11px 16px; border-radius: 9px;
       border: 1px solid var(--line); background: var(--card); color: var(--ink); cursor: pointer; min-height: 44px; }
.btn.primary { background: var(--ink); border-color: var(--ink); color: var(--bg); flex: 1; }
.btn:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }

/* ---------- timetable ---------- */
.tt-wrap { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 14px 12px 12px; overflow-x: auto; }
.tt { display: grid; grid-template-columns: 30px repeat(5, minmax(50px, 1fr)); gap: 3px; min-width: 296px; }
.tt-head { font-size: 9.5px; font-weight: 700; letter-spacing: .07em; color: var(--faint); text-align: center; padding-bottom: 5px; }
.tt-head.now { color: var(--ink); }
.tt-hours { position: relative; }
.tt-hours i { position: absolute; right: 3px; transform: translateY(-50%); font-family: var(--mono);
              font-size: 9px; font-style: normal; color: var(--faint); }
.tt-col { position: relative; border-left: 1px solid var(--hair); }
.tt-col.now { background: var(--sunken); border-radius: 5px; }
.blk { position: absolute; left: 1px; right: 1px; border-radius: 5px; background: var(--c);
       padding: 3px 3px 0; font-size: 9px; font-weight: 650; line-height: 1.15; overflow: hidden; color: #fff; }
.blk b { display: block; font-family: var(--mono); font-weight: 600; opacity: .8; font-size: 8.5px; }
:root:not([data-theme="light"]) .blk { color: #14161A; }
@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) .blk { color: #fff; } }
:root[data-theme="light"] .blk { color: #fff; }
:root[data-theme="dark"] .blk { color: #14161A; }

/* ---------- courses ---------- */
.courses { display: flex; flex-direction: column; gap: 7px; }
.course { background: var(--card); border-radius: 12px; box-shadow: var(--shadow); padding: 13px 14px;
          display: flex; flex-direction: column; gap: 9px; border-left: 3px solid var(--c, var(--line)); }
.c-top { display: flex; align-items: baseline; gap: 9px; }
.c-name { font-size: 14.5px; font-weight: 600; flex: 1; line-height: 1.3; }
.c-count { font-family: var(--mono); font-size: 10.5px; color: var(--faint); white-space: nowrap; }
.c-meta { font-size: 12px; color: var(--faint); }
.wbar { display: flex; height: 6px; border-radius: 4px; overflow: hidden; background: var(--sunken); }
.wbar span { display: block; }
.wleg { display: flex; flex-wrap: wrap; gap: 3px 11px; font-size: 10.5px; color: var(--faint); }
.wleg i { font-style: normal; font-family: var(--mono); }

footer { font-size: 11.5px; color: var(--faint); line-height: 1.7; border-top: 1px solid var(--line); padding-top: 13px; }
footer .btn { margin-bottom: 11px; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
"""


# --------------------------------------------------------------------------
# client script
# --------------------------------------------------------------------------

JS = r"""
'use strict';
var K = 'mestrado-2026-2';
var store = { override: {}, added: [], version: 1 };
var lsOK = true;
var filter = { mode: 'all', day: null };
var openIds = {};

var DOW = ['SEG','TER','QUA','QUI','SEX','SÁB','DOM'];
var MON = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
var TYPES = { assignment:'Trabalho', exam:'Prova', reading:'Leitura', paper:'Artigo',
              presentation:'Seminário', admin:'Pendência' };
var DAYK = ['mon','tue','wed','thu','fri','sat','sun'];

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
  });
}
function ymd(d) {
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}
function parseISO(iso) { var p = String(iso).split('-').map(Number); return new Date(p[0], p[1]-1, p[2]); }
var TODAY = parseISO(DATA.today);
function diffDays(iso) { return Math.round((parseISO(iso) - TODAY) / 86400000); }
function fmtShort(iso) { var d = parseISO(iso); return DOW[d.getDay()===0?6:d.getDay()-1].toLowerCase() + ' ' + d.getDate() + ' ' + MON[d.getMonth()]; }

function loadStore() {
  try {
    var raw = localStorage.getItem(K);
    if (raw) {
      var p = JSON.parse(raw);
      if (p && typeof p === 'object') {
        store.override = p.override || {};
        store.added = Array.isArray(p.added) ? p.added : [];
      }
    }
  } catch (e) { lsOK = false; }
}
function saveStore() {
  try { localStorage.setItem(K, JSON.stringify(store)); }
  catch (e) { lsOK = false; renderBanner(); }
}

function courseOf(id) {
  for (var i = 0; i < DATA.courses.length; i++) if (DATA.courses[i].id === id) return DATA.courses[i];
  return { id: 'none', name: 'Sem disciplina' };
}
function sev(t) {
  if (t.status === 'done') return 'done';
  if (t.days == null) return 'calm';
  if (t.days < 0) return 'late';
  if (t.days === 0) return 'now';
  if (t.days <= 3) return 'soon';
  return 'calm';
}
function countdown(n) {
  if (n == null) return 'sem data';
  if (n < 0) return Math.abs(n) + 'd atrasado';
  if (n === 0) return 'hoje';
  if (n === 1) return 'amanhã';
  return n + ' dias';
}

function allTasks() {
  var raw = DATA.tasks.concat(store.added);
  return raw.map(function (t) {
    var st = Object.prototype.hasOwnProperty.call(store.override, t.id) ? store.override[t.id] : t.status;
    var o = {};
    for (var k in t) o[k] = t[k];
    o.status = st;
    o.days = t.due ? diffDays(t.due) : null;
    o.course_name = t.course_name || courseOf(t.course).name;
    o.sev = sev(o);
    return o;
  }).sort(function (a, b) {
    if ((a.status === 'done') !== (b.status === 'done')) return a.status === 'done' ? 1 : -1;
    if ((a.days == null) !== (b.days == null)) return a.days == null ? 1 : -1;
    if (a.days == null) return 0;
    return a.days - b.days;
  });
}

/* ---------- hero + gauge ---------- */
function renderHero() {
  var open = allTasks().filter(function (t) { return t.status !== 'done'; });
  var t = open[0];
  var el = document.getElementById('hero');
  if (!t) {
    el.style.removeProperty('--c');
    el.innerHTML = '<div class="hero-label">Tudo em ordem</div><div class="hero-title">Nenhuma atividade em aberto.</div>';
    return;
  }
  var num, unit;
  if (t.days == null) { num = '—'; unit = 'sem data'; }
  else if (t.days < 0) { num = Math.abs(t.days); unit = 'dias atrasado'; }
  else if (t.days === 0) { num = 'hoje'; unit = ''; }
  else { num = t.days; unit = t.days === 1 ? 'dia' : 'dias'; }

  var meta = esc(t.course_name);
  if (t.due) meta += ' &middot; ' + fmtShort(t.due);
  if (t.due_time) meta += ' &middot; ' + esc(t.due_time);

  var late = open.filter(function (x) { return x.days != null && x.days < 0; });
  var extra = '';
  if (late.length > 1 || (late.length === 1 && late[0].id !== t.id)) {
    extra = '<div class="note-box bad">' + WARN + '<span>' + late.length + ' atividade(s) em atraso.</span></div>';
  }

  el.style.setProperty('--c', 'var(--c-' + t.course + ')');
  el.innerHTML =
    '<div class="hero-label">Próxima entrega</div>' +
    '<div class="hero-main"><div><div class="hero-num"' +
      (num === 'hoje' ? ' style="font-size:clamp(28px,7.5vw,38px)"' : '') + '>' + esc(num) + '</div>' +
      '<span class="hero-unit">' + esc(unit) + '</span></div>' +
    '<div><div class="hero-title">' + esc(t.title) + '</div><div class="hero-meta">' + meta + '</div></div></div>' +
    renderGauge(open) + extra;
}

function availableHours(n) {
  var h = 0;
  for (var i = 0; i < n; i++) {
    var d = new Date(TODAY.getTime() + i * 86400000);
    h += DATA.capacity[DAYK[d.getDay() === 0 ? 6 : d.getDay() - 1]] || 0;
  }
  return h;
}
function renderGauge(open) {
  var need = open.filter(function (t) { return t.days != null && t.days >= 0 && t.days <= 14; })
                 .reduce(function (a, t) { return a + (t.effort || 0); }, 0);
  var have = availableHours(14);
  var pct = have > 0 ? Math.min(100, 100 * need / have) : 100;
  var over = need > have;
  return '<div class="gauge"><div class="gauge-row"><span class="gauge-lab">Próximos 14 dias</span>' +
    '<span class="gauge-val"' + (over ? ' style="color:var(--danger)"' : '') + '>' + need + 'h / ' + have + 'h</span></div>' +
    '<div class="gauge-track"><span class="' + (over ? 'gauge-over' : 'gauge-fill') + '" style="width:' + pct.toFixed(1) + '%"></span></div>' +
    '<div class="gauge-row"><span class="gauge-lab" style="font-size:11.5px">' +
    (over ? 'trabalho necessário acima das horas disponíveis' : 'dentro das horas disponíveis') +
    '</span></div></div>';
}

/* ---------- calendar ---------- */
function renderCal() {
  var tasks = allTasks();
  var byDay = {};
  tasks.forEach(function (t) {
    if (!t.due) return;
    (byDay[t.due] = byDay[t.due] || []).push(t);
  });

  var start = new Date(TODAY.getTime());
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));   // Monday of this week

  var h = '';
  for (var i = 0; i < 7; i++) h += '<div class="cal-dow">' + DOW[i] + '</div>';
  for (var i = 0; i < 42; i++) {
    var d = new Date(start.getTime() + i * 86400000);
    var iso = ymd(d);
    var items = byDay[iso] || [];
    var opens = items.filter(function (t) { return t.status !== 'done'; });
    var cls = 'cal-cell';
    if (opens.length) cls += ' has';
    if (iso === DATA.today) cls += ' today';
    if (d < TODAY) cls += ' past';
    if ((DATA.capacity[DAYK[d.getDay() === 0 ? 6 : d.getDay() - 1]] || 0) === 0) cls += ' nostudy';
    var dots = '';
    opens.slice(0, 3).forEach(function (t) {
      dots += '<i style="--dc:var(--c-' + t.course + ')"></i>';
    });
    // Label the 1st so a six-week strip crossing into the next month stays readable.
    var mlab = d.getDate() === 1 ? '<span class="mlab">' + MON[d.getMonth()] + '</span>' : '';
    h += '<button class="' + cls + '" data-day="' + iso + '" aria-pressed="' +
         (filter.mode === 'day' && filter.day === iso) + '" aria-label="' + iso + ', ' +
         opens.length + ' atividades"><span class="n">' + d.getDate() + '</span>' + mlab +
         '<span class="cal-dots">' + dots + '</span></button>';
  }
  document.getElementById('calgrid').innerHTML = h;
  document.querySelectorAll('[data-day]').forEach(function (b) {
    b.addEventListener('click', function () {
      var iso = b.getAttribute('data-day');
      if (filter.mode === 'day' && filter.day === iso) { filter = { mode: 'all', day: null }; }
      else { filter = { mode: 'day', day: iso }; }
      render();
      document.getElementById('lista').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

/* ---------- list ---------- */
function passes(t) {
  if (filter.mode === 'day') return t.due === filter.day;
  if (filter.mode === '7') return t.days != null && t.days >= 0 && t.days <= 7 && t.status !== 'done';
  if (filter.mode === '14') return t.days != null && t.days >= 0 && t.days <= 14 && t.status !== 'done';
  if (filter.mode === 'late') return t.days != null && t.days < 0 && t.status !== 'done';
  if (filter.mode === 'done') return t.status === 'done';
  return t.status !== 'done';
}

var CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12.5l5.5 5.5L20 6.5"/></svg>';
var WARN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><path d="M12 3l9 16H3z"/><path d="M12 10v4"/><path d="M12 17v.4"/></svg>';

function renderList() {
  var tasks = allTasks().filter(passes);
  var el = document.getElementById('lista');
  if (!tasks.length) {
    el.innerHTML = '<p class="empty">Nenhuma atividade neste filtro.</p>';
    return;
  }
  el.innerHTML = tasks.map(function (t) {
    var sub = (TYPES[t.type] || 'Item') + ' &middot; ' + esc(t.course_name);
    if (t.due) sub += ' &middot; ' + fmtShort(t.due);
    if (t.effort) sub += ' &middot; ' + t.effort + 'h';
    var mine = t.mine ? '<span class="badge-mine">minha</span>' : '';
    var del = t.mine ? '<button class="it-del" data-del="' + esc(t.id) + '" aria-label="Remover">remover</button>' : '';
    var note = t.notes ? '<p class="it-note">' + esc(t.notes) + del + '</p>'
                       : (t.mine ? '<p class="it-note">' + del + '</p>' : '');
    return '<div class="item ' + t.sev + (t.status === 'done' ? ' done' : '') +
      (openIds[t.id] ? ' open' : '') + '" style="--c:var(--c-' + esc(t.course) + ')">' +
      '<div class="it-row">' +
      '<button class="box" data-toggle="' + esc(t.id) + '" role="checkbox" aria-checked="' +
        (t.status === 'done') + '" aria-label="Concluir ' + esc(t.title) + '">' + CHECK + '</button>' +
      '<div class="it-main" data-expand="' + esc(t.id) + '">' +
        '<div class="it-title">' + esc(t.title) + mine + '</div>' +
        '<div class="it-sub">' + sub + '</div></div>' +
      '<span class="pill">' + esc(countdown(t.days)) + '</span></div>' + note + '</div>';
  }).join('');

  el.querySelectorAll('[data-toggle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var id = b.getAttribute('data-toggle');
      var cur = allTasks().filter(function (x) { return x.id === id; })[0];
      store.override[id] = (cur && cur.status === 'done') ? 'todo' : 'done';
      saveStore(); render();
    });
  });
  el.querySelectorAll('[data-expand]').forEach(function (b) {
    b.addEventListener('click', function () {
      var id = b.getAttribute('data-expand');
      openIds[id] = !openIds[id];
      render();
    });
  });
  el.querySelectorAll('[data-del]').forEach(function (b) {
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      var id = b.getAttribute('data-del');
      store.added = store.added.filter(function (t) { return t.id !== id; });
      delete store.override[id];
      saveStore(); render();
    });
  });
}

function renderChips() {
  var modes = [['all','Em aberto'],['7','7 dias'],['14','14 dias'],['late','Atrasado'],['done','Concluídas']];
  var h = modes.map(function (m) {
    return '<button class="chip" data-mode="' + m[0] + '" aria-pressed="' +
      (filter.mode === m[0]) + '">' + m[1] + '</button>';
  }).join('');
  if (filter.mode === 'day') {
    h += '<button class="chip clear" data-mode="all" aria-pressed="false">' +
         fmtShort(filter.day) + ' &times;</button>';
  }
  var el = document.getElementById('chips');
  el.innerHTML = h;
  el.querySelectorAll('[data-mode]').forEach(function (b) {
    b.addEventListener('click', function () {
      filter = { mode: b.getAttribute('data-mode'), day: null };
      render();
    });
  });
}

function renderBanner() {
  var el = document.getElementById('banner');
  if (lsOK) { el.innerHTML = ''; return; }
  el.innerHTML = '<div class="note-box warn">' + WARN +
    '<span>Este navegador não permite salvar alterações no aparelho. ' +
    'Use <b>Exportar</b> antes de fechar a página, ou me avise pelo chat.</span></div>';
}

/* ---------- add form ---------- */
function initForm() {
  var sel = document.getElementById('f-course');
  sel.innerHTML = DATA.courses.map(function (c) {
    return '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>';
  }).join('');
  document.getElementById('f-due').value = DATA.today;

  document.getElementById('addbtn').addEventListener('click', function () {
    var f = document.getElementById('form');
    f.classList.toggle('open');
    if (f.classList.contains('open')) document.getElementById('f-title').focus();
  });
  document.getElementById('f-cancel').addEventListener('click', function () {
    document.getElementById('form').classList.remove('open');
  });
  document.getElementById('form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var title = document.getElementById('f-title').value.trim();
    if (!title) return;
    store.added.push({
      id: 'u' + Date.now().toString(36),
      title: title,
      course: sel.value,
      type: document.getElementById('f-type').value,
      due: document.getElementById('f-due').value || null,
      due_time: '',
      effort: Number(document.getElementById('f-effort').value) || 0,
      status: 'todo',
      notes: '',
      mine: true
    });
    saveStore();
    document.getElementById('f-title').value = '';
    document.getElementById('f-effort').value = '2';
    document.getElementById('form').classList.remove('open');
    filter = { mode: 'all', day: null };
    render();
  });
}

/* ---------- export ---------- */
function initExport() {
  var btn = document.getElementById('exportbtn');
  btn.addEventListener('click', async function () {
    var payload = {
      exported_at: new Date().toISOString(),
      note: 'Envie este arquivo no chat para sincronizar com o repositório.',
      concluidas: Object.keys(store.override).filter(function (k) { return store.override[k] === 'done'; }),
      reabertas: Object.keys(store.override).filter(function (k) { return store.override[k] === 'todo'; }),
      novas: store.added
    };
    var data = JSON.stringify(payload, null, 2);
    var dl = null;
    try { dl = await window.claude.use('downloads'); } catch (e) { dl = null; }
    if (!dl) { showExportFallback(data); return; }
    try {
      await dl.save({ filename: 'atividades-mestrado.json', data: data });
      btn.textContent = 'Exportado ✓';
      setTimeout(function () { btn.textContent = 'Exportar alterações'; }, 2500);
    } catch (err) {
      if (err && err.code === 'declined') return;
      showExportFallback(data);
    }
  });
}
function showExportFallback(data) {
  var box = document.getElementById('fallback');
  box.innerHTML = '<p style="font-size:12.5px;color:var(--muted);margin:8px 0 6px">' +
    'Não foi possível salvar o arquivo. Copie o texto abaixo e cole no chat:</p>' +
    '<textarea readonly style="width:100%;min-height:130px;font-family:var(--mono);font-size:11px;' +
    'padding:10px;border-radius:9px;border:1px solid var(--line);background:var(--bg);color:var(--ink)">' +
    esc(data) + '</textarea>';
  box.querySelector('textarea').select();
}

/* ---------- boot ---------- */
function render() { renderHero(); renderCal(); renderChips(); renderList(); renderBanner(); }
loadStore();
initForm();
initExport();
render();
"""


# --------------------------------------------------------------------------
# server-rendered fragments
# --------------------------------------------------------------------------

def color_tokens(courses: list[dict]) -> str:
    light = "".join(f"  --c-{c.get('id')}: {c.get('color', '#666')};\n" for c in courses)
    dark = "".join(f"  --c-{c.get('id')}: {c.get('color_dark', c.get('color', '#999'))};\n" for c in courses)
    return (
        f":root {{\n{light}  --c-none: #8B92A0;\n}}\n"
        f"@media (prefers-color-scheme: dark) {{\n :root:not([data-theme=\"light\"]) {{\n{dark} }}\n}}\n"
        f":root[data-theme=\"dark\"] {{\n{dark}}}\n"
    )


def render_timetable(m: dict) -> str:
    span = TIMETABLE_END - TIMETABLE_START
    height = span / 60 * 26
    hours = "".join(
        f'<i style="top:{100 * (h * 60 - TIMETABLE_START) / span:.3f}%">{h}h</i>'
        for h in range(8, 22, 2)
    )
    todays_key = DAY_KEYS[m["today"].weekday()]

    heads = '<div class="tt-head"></div>'
    for k in WEEKDAYS:
        heads += f'<div class="tt-head{" now" if k == todays_key else ""}">{DAY_PT[k]}</div>'

    cols = f'<div class="tt-hours" style="height:{height:.0f}px">{hours}</div>'
    for k in WEEKDAYS:
        placed, lanes = assign_lanes(m["week"][k])
        blocks = ""
        for item, lane in placed:
            slot, course = item["slot"], item["course"]
            s, e = minutes(slot.get("start")), minutes(slot.get("end"))
            w = 100 / lanes
            blocks += (
                f'<div class="blk" style="--c:var(--c-{course.get("id")});'
                f'top:{100 * (s - TIMETABLE_START) / span:.3f}%;'
                f'height:{100 * (e - s) / span:.3f}%;'
                f'left:{lane * w:.3f}%;width:{w:.3f}%">'
                f'<b>{esc(slot.get("start"))}</b>{esc(course.get("name"))}</div>'
            )
        cols += (f'<div class="tt-col{" now" if k == todays_key else ""}" '
                 f'style="height:{height:.0f}px">{blocks}</div>')

    note = ""
    if m["clashes"]:
        pairs = "; ".join(f"{a} × {b}" for v in m["clashes"].values() for a, b in v)
        note = (f'<div class="note-box warn" style="margin-top:12px">'
                f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                f'stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><path d="M12 3l9 16H3z"/>'
                f'<path d="M12 10v4"/><path d="M12 17v.4"/></svg>'
                f'<span>Choque de horário: {esc(pairs)}</span></div>')

    return (f'<section><h2>Semana de aulas</h2><div class="tt-wrap">'
            f'<div class="tt">{heads}{cols}</div>{note}</div></section>')


def render_courses(m: dict) -> str:
    cards = ""
    for c in m["courses"]:
        cid = c.get("id")
        mine = [t for t in m["tasks"] if t["course"] == cid]
        open_n = len([t for t in mine if t["status"] != "done"])

        meta = []
        if c.get("professor"):
            meta.append(esc(c["professor"]))
        for s in (c.get("schedule") or []):
            meta.append(f'{DAY_PT.get((s.get("day") or "").lower(), "")} {esc(s.get("start"))}')
        ends = as_date(c.get("ends"))
        if ends:
            meta.append(f"até {br_date(ends)}")

        grading = c.get("grading") or []
        total = sum(g.get("weight") or 0 for g in grading)
        bar = leg = ""
        if total:
            segs, legs = [], []
            for i, g in enumerate(grading):
                w = g.get("weight") or 0
                if w <= 0:
                    continue
                segs.append(f'<span style="width:{100 * w / total:.3f}%;'
                            f'background:var(--c-{cid});opacity:{1 - i * 0.18:.2f}"></span>')
                legs.append(f'<span>{esc(g.get("item"))} <i>{w}%</i></span>')
            bar = f'<div class="wbar">{"".join(segs)}</div>'
            leg = f'<div class="wleg">{"".join(legs)}</div>'
        else:
            leg = '<div class="wleg"><span>pesos ainda desconhecidos</span></div>'

        cards += (
            f'<div class="course" style="--c: var(--c-{cid})">'
            f'<div class="c-top"><div class="c-name">{esc(c.get("name"))}</div>'
            f'<div class="c-count">{open_n} aberto{"s" if open_n != 1 else ""}</div></div>'
            f'<div class="c-meta">{" &middot; ".join(meta)}</div>{bar}{leg}</div>'
        )
    return f'<section><h2>Disciplinas</h2><div class="courses">{cards}</div></section>'


def payload(m: dict) -> str:
    return json.dumps({
        "today": m["today"].isoformat(),
        "capacity": m["capacity"],
        "courses": [{"id": c.get("id"), "name": c.get("name")} for c in m["courses"]],
        "tasks": m["tasks"],
    }, ensure_ascii=False, separators=(",", ":"))


def render_html(m: dict) -> str:
    today = m["today"]
    heading = f"{FULLDAY_PT[today.weekday()]}, {today.day} de {FULLMONTH_PT[today.month - 1]}"
    types = "".join(f'<option value="{k}">{v}</option>' for k, v in TYPE_PT.items())

    return f"""<title>Painel do Mestrado</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#F5F6F8">
<style>{CSS}{color_tokens(m['courses'])}</style>
<div class="page">
  <header>
    <div class="term">{esc(m['term'])} &middot; UFSC &middot; 5 disciplinas</div>
    <h1>{heading}</h1>
  </header>

  <div id="banner"></div>
  <section class="hero" id="hero"></section>

  <section>
    <h2>Calendário de entregas</h2>
    <div class="cal">
      <div class="cal-grid" id="calgrid"></div>
      <div class="cal-legend">
        Toque num dia para ver as atividades daquele dia &middot; ponto = uma atividade,
        na cor da disciplina &middot; dia <span style="text-decoration:underline dotted;
        text-underline-offset:3px">sublinhado</span> = sem horário de estudo disponível.
      </div>
    </div>
  </section>

  <section>
    <div class="sec-head"><h2>Atividades</h2></div>
    <div class="chips" id="chips"></div>
    <div class="list" id="lista"></div>

    <button class="add-btn" id="addbtn">+ Nova atividade</button>
    <form class="form" id="form">
      <div class="field">
        <label for="f-title">O que é</label>
        <input id="f-title" type="text" placeholder="ex.: Ler artigo sobre BDI" required>
      </div>
      <div class="field">
        <label for="f-course">Disciplina</label>
        <select id="f-course"></select>
      </div>
      <div class="form-2">
        <div class="field">
          <label for="f-due">Prazo</label>
          <input id="f-due" type="date">
        </div>
        <div class="field">
          <label for="f-effort">Horas</label>
          <input id="f-effort" type="number" min="0" max="99" step="1" value="2">
        </div>
      </div>
      <div class="field">
        <label for="f-type">Tipo</label>
        <select id="f-type">{types}</select>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn primary">Adicionar</button>
        <button type="button" class="btn" id="f-cancel">Cancelar</button>
      </div>
    </form>
  </section>

  {render_timetable(m)}
  {render_courses(m)}

  <footer>
    <button class="btn" id="exportbtn">Exportar alterações</button>
    <div id="fallback"></div>
    O que você marca e adiciona aqui fica salvo <b>neste aparelho</b>. Para gravar no
    repositório de vez, exporte e me envie o arquivo no chat.<br>
    Atualizado em {dt.datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC &middot;
    contagens relativas a {today.strftime('%d/%m/%Y')} em {esc(m['tz'])}.
  </footer>
</div>
<script>var DATA = {payload(m)};</script>
<script>{JS}</script>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", action="store_true",
                    help="print the plain-text daily brief instead of building HTML")
    args = ap.parse_args()

    model = build_model(*load())

    if args.brief:
        print(brief(model))
        return

    out = HERE / "dashboard.html"
    out.write_text(render_html(model), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
