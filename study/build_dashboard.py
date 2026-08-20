#!/usr/bin/env python3
"""Build the term dashboard from courses.yml + tasks.yml.

Usage:
    python3 study/build_dashboard.py            # writes study/dashboard.html
    python3 study/build_dashboard.py --brief    # prints the plain-text daily brief

The page renders client-side from a baked JSON payload. It suggests what to
study each day by walking deadlines in order and spending study DAYS, never
invented hour counts: no teaching plan states how long a deliverable takes, so
activities carry a rough size (pequeno / medio / grande) instead. Viewer edits
live in device storage; the YAML files stay the source of truth and are
reconciled from the page's export file.
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

SIZE_PT = {"pequeno": "Pequeno", "medio": "Médio", "grande": "Grande"}
SIZE_DAYS = {"pequeno": 1, "medio": 3, "grande": 6}   # study days an activity needs

TIMETABLE_START = 8 * 60
TIMETABLE_END = 21 * 60
DEFAULT_WEIGHT = 15   # used when a plan has not published its weights yet


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


def ink_on(hex_color: str) -> str:
    """Pick readable text for a filled swatch, so yellow blocks get dark text
    and blue ones get light text instead of one global guess."""
    h = (hex_color or "#888").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#14161a" if lum > 0.42 else "#ffffff"


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
            "size": (raw.get("size") or "medio").lower(),
            "weight": raw.get("weight"),
            "status": (raw.get("status") or "todo").lower(),
            "notes": " ".join((raw.get("notes") or "").split()),
            "steps": [str(s) for s in (raw.get("steps") or [])],
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


# --------------------------------------------------------------------------
# plain-text brief (used by the scheduled morning push)
# --------------------------------------------------------------------------

def brief(m: dict) -> str:
    today = m["today"]
    opens = open_tasks(m)
    late = [x for x in opens if x["days"] is not None and x["days"] < 0]
    next7 = [x for x in opens if x["days"] is not None and 0 <= x["days"] <= 7]
    next14 = [x for x in opens if x["days"] is not None and 0 <= x["days"] <= 14]

    lines = [f"{FULLDAY_PT[today.weekday()]}, {today.day} de {FULLMONTH_PT[today.month - 1]}"]

    if late:
        lines += ["", f"ATRASADO ({len(late)}):"]
        lines += [f"  - {x['title']} [{x['course_name']}] {countdown(x['days'])}" for x in late]

    todays = m["week"][DAY_KEYS[today.weekday()]]
    if todays:
        lines += ["", "Aulas hoje:"]
        for item in todays:
            s = item["slot"]
            where = f" ({s.get('where')})" if s.get("where") else ""
            lines.append(f"  - {s.get('start','')}-{s.get('end','')} {item['course']['name']}{where}")
    else:
        lines += ["", "Sem aulas hoje."]

    if m["capacity"][DAY_KEYS[today.weekday()]] == 0:
        lines += ["", "Hoje nao tem horario de estudo previsto."]

    if next7:
        lines += ["", f"Proximos 7 dias ({len(next7)} entregas):"]
        lines += [f"  - {countdown(x['days']):>12}  {x['title']} [{x['course_name']}]"
                  f" ({SIZE_PT.get(x['size'], x['size']).lower()})" for x in next7]
    else:
        lines += ["", "Nada nos proximos 7 dias."]

    if len(next14) > len(next7):
        lines += ["", f"Proximos 14 dias: {len(next14)} entregas."]

    # Study days, not hours: this is the student's own availability, not a guess.
    study_days = sum(1 for i in range(14)
                     if m["capacity"][DAY_KEYS[(today + dt.timedelta(days=i)).weekday()]] > 0)
    big = [x for x in next14 if x["size"] == "grande"]
    if big:
        lines += ["", f"ATENCAO: {len(big)} entrega(s) grande(s) em 14 dias, "
                      f"com {study_days} dias de estudo disponiveis."]

    return "\n".join(lines)


# --------------------------------------------------------------------------
# stylesheet
# --------------------------------------------------------------------------

CSS = """
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: light;
  --bg:     #F4F5F7;
  --card:   #FFFFFF;
  --sunken: #E9EBEF;
  --ink:    #14161B;
  --muted:  #575E6B;
  --faint:  #868D9B;
  --line:   #E1E4EA;
  --hair:   #EDEFF3;

  --danger: #A62B1F;
  --danger-soft: #FBE8E5;
  --warn:   #855C00;
  --warn-soft: #FBF1D9;
  --ok:     #17654A;
  --ok-soft: #E3F1EA;

  --shadow: 0 1px 2px rgba(20,22,27,.05), 0 4px 14px -8px rgba(20,22,27,.12);
  --r: 14px;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg:     #0E1013;
    --card:   #191C21;
    --sunken: #23272E;
    --ink:    #EDEFF3;
    --muted:  #A2AAB8;
    --faint:  #737B89;
    --line:   #2A2F37;
    --hair:   #222630;

    --danger: #FF8C7A;
    --danger-soft: #3A1C17;
    --warn:   #F0BE5C;
    --warn-soft: #33280E;
    --ok:     #5FD39C;
    --ok-soft: #14291F;

    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 6px 18px -10px rgba(0,0,0,.6);
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg:     #0E1013;
  --card:   #191C21;
  --sunken: #23272E;
  --ink:    #EDEFF3;
  --muted:  #A2AAB8;
  --faint:  #737B89;
  --line:   #2A2F37;
  --hair:   #222630;

  --danger: #FF8C7A;
  --danger-soft: #3A1C17;
  --warn:   #F0BE5C;
  --warn-soft: #33280E;
  --ok:     #5FD39C;
  --ok-soft: #14291F;

  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 6px 18px -10px rgba(0,0,0,.6);
}

body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--sans); font-size: 16px; line-height: 1.5;
  -webkit-font-smoothing: antialiased; -webkit-text-size-adjust: 100%;
}
.page { max-width: 760px; margin: 0 auto; padding: 22px 0 80px; display: flex; flex-direction: column; gap: 26px; }
.px { padding-left: 16px; padding-right: 16px; }
.term { font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--faint); }
h1 { font-size: clamp(21px,5.4vw,27px); font-weight: 650; letter-spacing: -.02em; margin: 2px 0 0; text-wrap: balance; }
h2 { font-size: 12.5px; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; color: var(--faint); margin: 0 0 10px; }
h2 .sub { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--faint); }

/* ---------- carousels ---------- */
.carousel {
  display: flex; gap: 10px; align-items: stretch; scroll-snap-type: x mandatory; scrollbar-width: none;
  padding: 2px 16px 4px;
  /* An explicit width plus min-width:0 keeps this scroll container from sizing
     to its off-screen cards and widening the whole document. */
  width: 100%; max-width: 100%; min-width: 0;
  overflow-x: auto; overflow-y: hidden;
}
section { min-width: 0; }
.carousel::-webkit-scrollbar { display: none; }
/* ---- outer carousel: one card per discipline ---- */
.disc-card {
  height: auto;
  /* min-width:0 is required: without it the flex item refuses to shrink below
     its min-content width and clips its own header text. */
  flex: 0 0 calc(100% - 32px); min-width: 0; scroll-snap-align: center;
  background: var(--card); border-radius: var(--r); box-shadow: var(--shadow);
  padding: 16px 0 12px; display: flex; flex-direction: column; gap: 12px;
  border-top: 3px solid var(--c, var(--line));
}
.dc-head { padding: 0 16px; display: flex; flex-direction: column; gap: 7px; }
.dc-top { display: flex; align-items: center; gap: 9px; }
.dc-tag { font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
          background: var(--c); color: var(--on-c, #fff); padding: 3px 7px; border-radius: 5px; }
.dc-name { font-size: 16.5px; font-weight: 630; line-height: 1.25; flex: 1; text-wrap: pretty; }
.dc-meta { font-size: 11.5px; color: var(--faint); line-height: 1.5; }
.dc-stats { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--muted); }
.dc-stats b { font-family: var(--mono); font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; }
.dc-grade { display: flex; flex-direction: column; gap: 5px; padding: 0 16px; }
.dc-sep { height: 1px; background: var(--hair); margin: 1px 0; }

/* ---- inner carousel: that discipline's activities ---- */
/* Fixed strip height plus stretched cards: every discipline's carousel is the
   same size, whatever its longest title happens to be. */
.acts { display: flex; gap: 8px; align-items: stretch; scroll-snap-type: x mandatory;
        scrollbar-width: none; overflow-x: auto; overflow-y: hidden; width: 100%;
        max-width: 100%; min-width: 0; padding: 0 16px 2px; overscroll-behavior-x: contain;
        height: 214px; }
.acts::-webkit-scrollbar { display: none; }
.act {
  flex: 0 0 calc(100% - 26px); scroll-snap-align: center; min-width: 0;
  background: var(--bg); border: 1px solid var(--line); border-radius: 11px;
  padding: 12px 13px; display: flex; flex-direction: column; gap: 8px;
}
.act-facts { flex: 1; }
.act-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
             overflow: hidden; }
.act-top { display: flex; align-items: center; gap: 8px; }
.act-type { font-size: 11px; font-weight: 650; color: var(--muted); }
.act-idx { font-family: var(--mono); font-size: 10px; font-weight: 700; color: var(--faint); margin-left: auto; }
.act-title { font-size: 14.5px; font-weight: 600; line-height: 1.3; text-wrap: pretty; }
.act-facts { display: flex; flex-direction: column; gap: 4px; }
.act-f { display: flex; align-items: baseline; gap: 6px; font-size: 12.5px; color: var(--muted); }
.act-f b { font-family: var(--mono); font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; }
.act-f.bad, .act-f.bad b { color: var(--danger); }
.sz { font-size: 9.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
       padding: 2px 6px; border-radius: 4px; background: var(--sunken); color: var(--muted); }
.sz-grande { background: var(--warn-soft); color: var(--warn); }
.dc-tight, .dc-tight b { color: var(--danger); }
.dr-tag { font-family: var(--mono); font-style: normal; font-size: 10px; font-weight: 700; color: var(--faint); }
.dr-why { font-size: 11px; color: var(--faint); margin-top: 2px; margin-bottom: 6px; }
.dr-item + .dr-why:last-child { margin-bottom: 0; }
.dr-errand { font-size: 11.5px; color: var(--muted); font-style: italic; margin-top: 2px; }
.it-peek { font-size: 11.5px; color: var(--faint); padding: 0 12px 11px; }
.act-foot { display: flex; gap: 7px; align-items: center; }
.act-done { font-size: 11.5px; color: var(--ok); font-weight: 600; }
.act-empty { flex: 0 0 calc(100% - 26px); scroll-snap-align: center; font-size: 13px;
             color: var(--faint); padding: 14px 2px; font-style: italic; }

/* ---- carousel navigation ---- */
.carnav { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 9px; }
.arrow { font: inherit; font-size: 15px; line-height: 1; width: 34px; height: 34px; border-radius: 50%;
         border: 1px solid var(--line); background: var(--card); color: var(--ink); cursor: pointer;
         display: grid; place-items: center; }
.arrow:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.arrow[disabled] { opacity: .35; cursor: default; }

.mini-card {
  flex: 0 0 74%; min-width: 0; scroll-snap-align: start; background: var(--card); border-radius: 12px;
  box-shadow: var(--shadow); padding: 12px 13px; border-left: 3px solid var(--c, var(--line));
  display: flex; flex-direction: column; gap: 5px;
}
.mini-when { font-family: var(--mono); font-size: 10.5px; font-weight: 700; color: var(--c); letter-spacing: .03em; }
.mini-title { font-size: 13.5px; font-weight: 550; line-height: 1.3; }
.mini-sub { font-size: 11.5px; color: var(--faint); }

.dots { display: flex; gap: 5px; justify-content: center; }
.dots button { width: 18px; height: 18px; padding: 0; border: 0; background: none; cursor: pointer;
               display: grid; place-items: center; }
.dots button:focus-visible { outline: 2px solid var(--ink); outline-offset: 0; border-radius: 4px; }
.dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--line); display: block; transition: background .15s; }
.dots button[aria-current="true"] i { background: var(--ink); }
.dots.inner { margin-top: 7px; }
.dots.inner i { width: 5px; height: 5px; }

/* ---------- plan chart ---------- */
.chart-card { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 16px 14px 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 5px 12px; margin-bottom: 14px; }
.lg { display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--muted); }
.lg i { width: 9px; height: 9px; border-radius: 2px; background: var(--lc); display: block; flex: none; }
.plot { display: grid; grid-template-columns: repeat(14, 1fr); gap: 3px; }
.fcell { aspect-ratio: 1 / 1.5; min-height: 34px; border-radius: 5px;
         background: var(--c); color: var(--on-c, #fff); display: grid; place-items: center;
         font-size: 8.5px; font-weight: 750; letter-spacing: .02em; }
.fcell { position: relative; overflow: hidden; }
.fbands { position: absolute; inset: 0; display: flex; flex-direction: column; }
.fbands i { flex: 1; display: block; }
.flab { position: relative; z-index: 1; color: var(--on-c, #fff); }
.fcell.empty { background: var(--sunken); color: var(--faint); font-size: 12px; }
.fcell.off { background: repeating-linear-gradient(135deg, var(--sunken) 0 4px, transparent 4px 8px); color: var(--faint); }
.paxis { display: grid; grid-template-columns: repeat(14, 1fr); gap: 3px; margin-top: 7px; }
.pax { font-size: 9px; text-align: center; color: var(--faint); line-height: 1.25; font-variant-numeric: tabular-nums; }
.pax b { display: block; font-weight: 700; font-size: 8.5px; letter-spacing: .02em; }
.pax.wknd { opacity: .5; }
.pax.today { color: var(--ink); font-weight: 700; }
.wk-tot { display: grid; grid-template-columns: 1fr 1fr; gap: 3px; margin-top: 10px; }
.wk-tot div { font-size: 11px; color: var(--muted); text-align: center; padding: 6px; background: var(--sunken); border-radius: 7px; }
.wk-tot b { font-family: var(--mono); color: var(--ink); font-variant-numeric: tabular-nums; }
.tip {
  position: absolute; z-index: 5; pointer-events: none; opacity: 0;
  background: var(--ink); color: var(--bg); font-size: 11.5px; line-height: 1.4;
  padding: 7px 9px; border-radius: 8px; max-width: 190px; transform: translate(-50%,-100%);
}
.tip.on { opacity: 1; }

/* ---------- day plan list ---------- */
.days { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.dayrow { display: flex; gap: 11px; align-items: flex-start; padding: 10px 12px; background: var(--card);
          border-radius: 10px; box-shadow: var(--shadow); }
.dayrow.rest { opacity: .6; }
.dr-when { flex: none; width: 58px; font-family: var(--mono); font-size: 11px; font-weight: 650; color: var(--muted); }
.dr-when b { display: block; font-size: 13px; color: var(--ink); }
/* min-width:0 on both levels is what lets the title ellipsis actually engage;
   without it a long title pushes the row wider than the page. */
.dr-items { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.dr-item { display: flex; align-items: center; gap: 7px; font-size: 12.5px; min-width: 0; }
.dr-item i { width: 8px; height: 8px; border-radius: 2px; background: var(--dc); flex: none; }
.dr-item span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dr-item b { font-family: var(--mono); font-size: 11.5px; color: var(--muted); }
.dr-free { font-size: 12.5px; color: var(--faint); font-style: italic; }

/* ---------- calendar ---------- */
.cal { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 15px 13px 13px; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.cal-dow { font-size: 9.5px; font-weight: 700; letter-spacing: .06em; color: var(--faint); text-align: center; padding-bottom: 5px; }
.cal-cell { position: relative; aspect-ratio: 1/1; min-height: 40px; border: 0; background: transparent;
            border-radius: 9px; display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 3px; font: inherit; font-size: 13px; color: var(--ink); cursor: pointer; padding: 2px; }
.cal-cell.past { opacity: .4; }
.cal-cell .mlab { font-size: 8px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--faint); line-height: 1; }
.cal-cell.has { background: var(--sunken); }
.cal-cell.today { box-shadow: inset 0 0 0 2px var(--ink); font-weight: 700; }
.cal-cell[aria-pressed="true"] { background: var(--ink); color: var(--bg); }
.cal-cell[aria-pressed="true"] .cnt { color: var(--bg); }
.cal-cell:focus-visible { outline: 2px solid var(--ink); outline-offset: 1px; }
.cal-cell .n { font-variant-numeric: tabular-nums; line-height: 1; }
.cal-cell .cnt { font-family: var(--mono); font-size: 9px; font-weight: 700; color: var(--muted); line-height: 1; }
.cal-cell.urg { background: var(--danger-soft); }
.cal-cell.urg .cnt { color: var(--danger); }
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
.it-row { display: flex; gap: 10px; align-items: center; padding: 11px 12px; }
.box { flex: none; width: 25px; height: 25px; border-radius: 7px; border: 1.8px solid var(--line);
       background: var(--card); cursor: pointer; display: grid; place-items: center; padding: 0; color: transparent;
       -webkit-tap-highlight-color: transparent;
       transition: background .12s ease, border-color .12s ease, transform .1s ease, color .12s ease; }
.box:hover { border-color: var(--muted); }
.box.pressed { background: var(--sunken); border-color: var(--muted); transform: scale(.88); }
.item.done .box.pressed { background: var(--ok); }
/* Held on screen just long enough for the tick to register before the row
   leaves the filter. */
.item.settling { transition: opacity .25s ease .32s, transform .25s ease .32s; opacity: .35; transform: scale(.985); }
.step { -webkit-tap-highlight-color: transparent; transition: background .12s ease; }
.step.pressed { background: var(--sunken); }
.step i { transition: background .12s ease, border-color .12s ease, color .12s ease; }
.tbtn { -webkit-tap-highlight-color: transparent; transition: background .12s ease, border-color .12s ease, transform .1s ease; }
.tbtn.pressed { background: var(--sunken); border-color: var(--muted); transform: scale(.96); }
.act.done { opacity: .55; }
.act.done .act-title { text-decoration: line-through; }
.box:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.item.done .box { background: var(--ok); border-color: var(--ok); color: var(--card); }
.it-main { flex: 1; min-width: 0; cursor: pointer; }
.it-title { font-size: 14.5px; font-weight: 550; line-height: 1.34; text-wrap: pretty; }
.it-sub { font-size: 11.5px; color: var(--faint); margin-top: 2px; display: flex; flex-wrap: wrap; gap: 2px 7px; align-items: center; }
.cbadge { font-size: 9.5px; font-weight: 700; letter-spacing: .04em; background: var(--c); color: var(--on-c, #fff);
          padding: 1px 5px; border-radius: 4px; }
.pill { flex: none; font-family: var(--mono); font-size: 10.5px; font-weight: 600; padding: 5px 8px;
        border-radius: 999px; background: var(--sunken); color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
.item.late .pill, .item.now .pill { background: var(--danger-soft); color: var(--danger); }
.item.soon .pill { background: var(--warn-soft); color: var(--warn); }
.item.done { opacity: .5; }
.item.done .it-title { text-decoration: line-through; }
.item.done .pill { background: var(--ok-soft); color: var(--ok); }
.it-foot { padding: 11px 12px 12px; border-top: 1px solid var(--hair); display: none; flex-direction: column; gap: 9px; }
.item.open .it-foot { display: flex; }
.it-note { font-size: 13.5px; color: var(--muted); margin: 0; line-height: 1.55; }
.it-acts { display: flex; gap: 7px; }
.tbtn { font: inherit; font-size: 12.5px; font-weight: 600; padding: 8px 12px; border-radius: 8px;
        border: 1px solid var(--line); background: var(--bg); color: var(--ink); cursor: pointer; min-height: 38px; }
.tbtn.danger { color: var(--danger); border-color: var(--danger); }
.tbtn:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.badge-mine { font-size: 9.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
              color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 1px 4px; }
.empty { font-size: 13.5px; color: var(--faint); padding: 16px 2px; }

/* ---------- form ---------- */
.add-btn { font: inherit; font-size: 14px; font-weight: 600; width: 100%; padding: 13px; border-radius: 12px;
           border: 1.5px dashed var(--line); background: var(--card); color: var(--muted); cursor: pointer; margin-top: 8px; }
.add-btn:hover { border-color: var(--muted); color: var(--ink); }
.add-btn:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.form { background: var(--card); border-radius: 12px; box-shadow: var(--shadow); padding: 15px; margin-top: 8px;
        display: none; flex-direction: column; gap: 11px; }
.form.open { display: flex; }
.form-title { font-size: 13px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--faint); }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 11.5px; font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--faint); }
.field input, .field select { font: inherit; font-size: 15px; padding: 10px 11px; border-radius: 9px;
  border: 1px solid var(--line); background: var(--bg); color: var(--ink); min-height: 44px; width: 100%; }
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
.blk { position: absolute; left: 1px; right: 1px; border-radius: 5px; background: var(--c); color: var(--on-c, #fff);
       padding: 3px 3px 0; font-size: 9px; font-weight: 650; line-height: 1.15; overflow: hidden; }
.blk b { display: block; font-family: var(--mono); font-weight: 700; opacity: .85; font-size: 8.5px; }

/* ---------- courses ---------- */
.courses { display: flex; flex-direction: column; gap: 7px; }
.course { background: var(--card); border-radius: 12px; box-shadow: var(--shadow); padding: 13px 14px;
          display: flex; flex-direction: column; gap: 9px; border-left: 3px solid var(--c, var(--line)); }
.c-top { display: flex; align-items: center; gap: 9px; }
.c-name { font-size: 14.5px; font-weight: 600; flex: 1; line-height: 1.3; }
.c-count { font-family: var(--mono); font-size: 10.5px; color: var(--faint); white-space: nowrap; }
.c-meta { font-size: 12px; color: var(--faint); }
.wbar { display: flex; height: 6px; border-radius: 4px; overflow: hidden; background: var(--sunken); gap: 2px; }
.wbar span { display: block; }
.wleg { display: flex; flex-wrap: wrap; gap: 3px 11px; font-size: 10.5px; color: var(--faint); }
.wleg i { font-style: normal; font-family: var(--mono); }

.brief { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 6px 14px 10px; }
.bf-row { display: flex; gap: 11px; align-items: flex-start; padding: 9px 0; border-bottom: 1px solid var(--hair); }
.bf-row:last-child { border-bottom: 0; }
.bf-row > div { flex: 1; min-width: 0; }
.bf-row.bad { color: var(--danger); }
.bf-row.bad b { font-weight: 650; }
.bf-row svg { flex: none; margin-top: 2px; }
.bf-k { flex: none; width: 54px; font-size: 10px; font-weight: 700; letter-spacing: .07em;
        text-transform: uppercase; color: var(--faint); padding-top: 3px; }
.bf-line { font-size: 13px; line-height: 1.45; display: flex; align-items: baseline; gap: 7px; }
.bf-line i { width: 7px; height: 7px; border-radius: 2px; background: var(--dc); flex: none; }
.bf-sub { font-size: 12.5px; font-weight: 500; margin-top: 2px; }
.bf-none { font-size: 13px; color: var(--faint); font-style: italic; }
.bf-when { font-style: normal; font-family: var(--mono); font-size: 10.5px; color: var(--faint); }
.bf-tight { font-style: normal; font-size: 10.5px; font-weight: 700; color: var(--danger); }
.pend { display: flex; align-items: center; gap: 10px; background: var(--warn-soft); color: var(--warn);
         border-radius: 10px; padding: 9px 10px 9px 13px; font-size: 12.5px; font-weight: 550; }
.pend span { flex: 1; }
.pend .tbtn { background: var(--card); border-color: var(--warn); color: var(--warn); min-height: 34px; padding: 6px 11px; }
.note-box { display: flex; gap: 9px; align-items: flex-start; border-radius: 10px; padding: 11px 13px; font-size: 13.5px; font-weight: 500; }
.note-box.bad { background: var(--danger-soft); color: var(--danger); }
.note-box.warn { background: var(--warn-soft); color: var(--warn); }
.note-box svg { flex: none; margin-top: 2px; }

/* ---------- day modal ---------- */
.scrim { position: fixed; inset: 0; background: rgba(8,9,11,.55); z-index: 40;
         display: none; align-items: center; justify-content: center; padding: 16px; }
.scrim.on { display: flex; }
.modal {
  background: var(--card); width: 100%; max-width: 520px; max-height: 80vh;
  border-radius: 16px; display: flex; flex-direction: column;
  box-shadow: 0 12px 48px rgba(0,0,0,.35); overflow: hidden;
}
.md-head { display: flex; align-items: center; gap: 10px; padding: 15px 14px 12px; border-bottom: 1px solid var(--hair); }
.md-nav { font: inherit; font-size: 16px; width: 34px; height: 34px; flex: none; border-radius: 50%;
          border: 1px solid var(--line); background: var(--bg); color: var(--ink); cursor: pointer; }
.md-nav[disabled] { opacity: .3; cursor: default; }
.md-title { flex: 1; min-width: 0; }
.md-title b { display: block; font-size: 16px; font-weight: 650; line-height: 1.2; }
.md-title span { font-size: 11.5px; color: var(--faint); }
.md-x { font: inherit; font-size: 20px; line-height: 1; width: 34px; height: 34px; flex: none; border-radius: 50%;
        border: 0; background: var(--sunken); color: var(--ink); cursor: pointer; }
.md-x:focus-visible, .md-nav:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.md-body { overflow-y: auto; padding: 12px 14px 20px; display: flex; flex-direction: column; gap: 8px;
           touch-action: pan-y; }
.md-hint { font-size: 11px; color: var(--faint); text-align: center; padding-top: 2px; }

/* ---------- steps / to-do ---------- */
.steps { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.steps-h { font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
           color: var(--faint); margin-bottom: 4px; }
.step { display: flex; gap: 9px; align-items: flex-start; padding: 7px 6px; border-radius: 8px;
        cursor: pointer; background: none; border: 0; font: inherit; text-align: left; width: 100%; color: var(--ink); }
.step:hover { background: var(--sunken); }
.step:focus-visible { outline: 2px solid var(--ink); outline-offset: -2px; }
.step i { flex: none; width: 17px; height: 17px; margin-top: 1px; border-radius: 5px;
          border: 1.6px solid var(--line); background: var(--card); display: grid; place-items: center;
          color: transparent; }
.step.on i { background: var(--ok); border-color: var(--ok); color: var(--card); }
.step span { flex: 1; font-size: 13px; line-height: 1.4; }
.step.on span { text-decoration: line-through; color: var(--faint); }
.step-prog { font-family: var(--mono); font-size: 10.5px; color: var(--faint); }

footer { font-size: 11.5px; color: var(--faint); line-height: 1.7; border-top: 1px solid var(--line); padding-top: 13px; }
footer .btn { margin-bottom: 11px; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; scroll-behavior: auto !important; } }
"""


# --------------------------------------------------------------------------
# client script
# --------------------------------------------------------------------------

JS = r"""
'use strict';
var K = 'mestrado-2026-2';
var store = { override: {}, edits: {}, added: [], steps: {}, version: 3 };
var lsOK = true;
var filter = { mode: 'all', day: null };
var openIds = {};
var editingId = null;
var DEFAULT_WEIGHT = 15;

var DOW = ['SEG','TER','QUA','QUI','SEX','SÁB','DOM'];
var MON = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
var FULLDOW = ['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'];
var FULLMON = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
var TYPES = { assignment:'Trabalho', exam:'Prova', reading:'Leitura', paper:'Artigo',
              presentation:'Seminário', admin:'Pendência' };
var DAYK = ['mon','tue','wed','thu','fri','sat','sun'];
var SIZE_PT = { pequeno:'Pequeno', medio:'Médio', grande:'Grande' };

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
  });
}
function ymd(d) {
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}
function parseISO(iso) { var p = String(iso).split('-').map(Number); return new Date(p[0], p[1]-1, p[2]); }
/* The date is worked out on the device, not baked in at build time. Baking it
   meant the page had to be republished every morning to stay correct, and each
   republish serves the page from a new versioned path, which is what was
   wiping the completions stored on the device overnight. */
function todayISO() {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: DATA.tz }).format(new Date());
  } catch (e) {
    return DATA.today;
  }
}
var TODAY_ISO = todayISO();
var TODAY = parseISO(TODAY_ISO);
function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
function diffDays(iso) { return Math.round((parseISO(iso) - TODAY) / 86400000); }
function dowKey(d) { return DAYK[d.getDay() === 0 ? 6 : d.getDay() - 1]; }
function capOf(d) { return DATA.capacity[dowKey(d)] || 0; }
function fmtShort(iso) { var d = parseISO(iso); return DOW[d.getDay()===0?6:d.getDay()-1].toLowerCase() + ' ' + d.getDate() + ' ' + MON[d.getMonth()]; }

function loadStore() {
  try {
    var raw = localStorage.getItem(K);
    if (raw) {
      var p = JSON.parse(raw);
      if (p && typeof p === 'object') {
        store.override = p.override || {};
        store.edits = p.edits || {};
        store.added = Array.isArray(p.added) ? p.added : [];
        store.steps = p.steps || {};
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
  return { id: 'none', name: 'Sem disciplina', abbr: '?' };
}
function sevOf(t) {
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
  return DATA.tasks.concat(store.added).map(function (t) {
    var o = {};
    for (var k in t) o[k] = t[k];
    var ed = store.edits[t.id];
    if (ed) for (var k2 in ed) o[k2] = ed[k2];
    if (Object.prototype.hasOwnProperty.call(store.override, t.id)) o.status = store.override[t.id];
    o.days = o.due ? diffDays(o.due) : null;
    o.course_name = courseOf(o.course).name;
    o.abbr = courseOf(o.course).abbr;
    o.sev = sevOf(o);
    o.edited = !!ed;
    return o;
  }).sort(function (a, b) {
    if ((a.status === 'done') !== (b.status === 'done')) return a.status === 'done' ? 1 : -1;
    if ((a.days == null) !== (b.days == null)) return a.days == null ? 1 : -1;
    if (a.days == null) return 0;
    return a.days - b.days;
  });
}

var HORIZON = 200;

/* Scheduler in STUDY DAYS, not hours. Each day with study time gets one focus,
   taken from the nearest deadline still unfinished; an activity occupies as
   many study days as its size implies. Nothing here claims to know how long
   anything takes; it orders the work and shows when a deadline arrives before
   enough study days do. */
function sizeDays(t) { return DATA.sizeDays[t.size] || DATA.sizeDays.medio || 3; }

/* How many activities a day can carry. A day with a full evening holds two;
   Tuesday, with only the hour at work, holds one. */
function slotsFor(day) { var c = capOf(day); return c <= 0 ? 0 : (c >= 3 ? 2 : 1); }

/* Admin items are questions to ask in class, not study work. Scheduling them
   as if they cost a study day each is what pushed the CD exam past its own
   date: three of them ate Monday through Thursday. */
function isStudyWork(t) { return t.status !== 'done' && t.due && t.type !== 'admin'; }

function schedule() {
  var queue = allTasks().filter(isStudyWork).sort(function (a, b) {
    if (a.due !== b.due) return a.due < b.due ? -1 : 1;
    return (b.weight == null ? DEFAULT_WEIGHT : b.weight) - (a.weight == null ? DEFAULT_WEIGHT : a.weight);
  });

  var need = {}, doneBy = {};
  queue.forEach(function (t) { need[t.id] = sizeDays(t); doneBy[t.id] = 0; });

  /* Several deadlines run in parallel, so each day takes the nearest ones that
     still have work left rather than finishing one activity before touching
     the next. That is what puts exam prep in the days before the exam. */
  var plan = {};
  for (var i = 0; i < HORIZON; i++) {
    var day = addDays(TODAY, i);
    var slots = slotsFor(day);
    if (!slots) continue;
    var iso = ymd(day);
    var picked = [];
    for (var j = 0; j < queue.length && picked.length < slots; j++) {
      var t = queue[j];
      if (need[t.id] <= 0) continue;
      // Never plan work for a day after its deadline. Something already
      // overdue is the exception: it still has to be done, as soon as possible.
      if (t.due < iso && t.days >= 0) continue;
      need[t.id] -= 1;
      picked.push(t.id);
      if (iso <= t.due) doneBy[t.id] += 1;
    }
    if (picked.length) plan[iso] = picked;
  }
  return { plan: plan, doneBy: doneBy };
}

/* Reminders that belong to a day but cost no study time. */
function classErrands(iso) {
  return allTasks().filter(function (t) {
    return t.type === 'admin' && t.status !== 'done' && t.due === iso;
  });
}

/* True when the deadline arrives before enough study days do. */
function isTight(t, sch) {
  if (!t.due || t.status === 'done' || t.type === 'admin') return false;
  return (sch.doneBy[t.id] || 0) < sizeDays(t);
}

/* ---------- today's brief, computed here rather than pushed from a job ----------
   Everything the morning message said is derived from the same data this page
   already has, so it belongs on the page: open it and the brief is current,
   with no conversation to go and read. */
function renderBrief(sch) {
  var el = document.getElementById('brief');
  var tasks = allTasks();
  var open = tasks.filter(function (t) { return t.status !== 'done'; });
  var late = open.filter(function (t) { return t.days != null && t.days < 0; });
  var today = open.filter(function (t) { return t.days === 0; });
  var next7 = open.filter(function (t) { return t.days != null && t.days > 0 && t.days <= 7; });

  var dayKey = DAYK[TODAY.getDay() === 0 ? 6 : TODAY.getDay() - 1];
  var classes = [];
  DATA.courses.forEach(function (c) {
    (c.schedule || []).forEach(function (s) {
      if (s.dayKey === dayKey) classes.push({ c: c, s: s });
    });
  });
  classes.sort(function (a, b) { return (a.s.start || '').localeCompare(b.s.start || ''); });

  var focus = (sch.plan[TODAY_ISO] || []).map(function (id) {
    return tasks.filter(function (x) { return x.id === id; })[0];
  }).filter(Boolean);
  var errands = classErrands(TODAY_ISO);

  var rows = '';
  if (late.length) {
    rows += '<div class="bf-row bad">' + WARN + '<div><b>' + late.length +
      (late.length === 1 ? ' atividade atrasada' : ' atividades atrasadas') + '</b><div class="bf-sub">' +
      esc(late.map(function (t) { return t.title; }).join(' &middot; ')) + '</div></div></div>';
  }
  if (today.length) {
    rows += '<div class="bf-row bad">' + WARN + '<div><b>Vence hoje</b><div class="bf-sub">' +
      esc(today.map(function (t) { return t.title; }).join(' &middot; ')) + '</div></div></div>';
  }

  rows += '<div class="bf-row"><span class="bf-k">Aulas</span><div>' +
    (classes.length ? classes.map(function (x) {
      return '<div class="bf-line"><i style="--dc:var(--c-' + esc(x.c.id) + ')"></i>' +
        esc(x.s.start) + '-' + esc(x.s.end) + '  ' + esc(x.c.name) +
        (x.s.where ? ' <em class="bf-when">' + esc(x.s.where) + '</em>' : '') + '</div>';
    }).join('') : '<span class="bf-none">sem aulas hoje</span>') + '</div></div>';

  rows += '<div class="bf-row"><span class="bf-k">Estudar</span><div>' +
    (focus.length ? focus.map(function (t) {
      return '<div class="bf-line"><i style="--dc:var(--c-' + esc(t.course) + ')"></i>' +
        esc(t.title) + (isTight(t, sch) ? ' <em class="bf-tight">prazo apertado</em>' : '') + '</div>';
    }).join('') : '<span class="bf-none">' +
      (capOf(TODAY) > 0 ? 'nada pendente' : 'sem horário de estudo hoje') + '</span>') + '</div></div>';

  if (errands.length) {
    rows += '<div class="bf-row"><span class="bf-k">Na aula</span><div>' +
      errands.map(function (t) { return '<div class="bf-line">' + esc(t.title) + '</div>'; }).join('') +
      '</div></div>';
  }

  rows += '<div class="bf-row"><span class="bf-k">7 dias</span><div>' +
    (next7.length ? next7.map(function (t) {
      return '<div class="bf-line"><i style="--dc:var(--c-' + esc(t.course) + ')"></i>' +
        esc(t.title) + ' <em class="bf-when">' + esc(countdown(t.days)) + '</em></div>';
    }).join('') : '<span class="bf-none">nada nos próximos 7 dias</span>') + '</div></div>';

  el.innerHTML = '<div class="brief">' + rows + '</div>';
}

/* ---------- outer carousel: disciplines, each holding its own activity carousel
   Order inside a discipline is simply by deadline, with no invented score. The one
   judgement shown is factual and comes from the scheduler: whether the hours
   still fit before the date. ---------- */
function renderDisciplines(sch) {
  var tasks = allTasks();
  var el = document.getElementById('disc');

  el.innerHTML = DATA.courses.map(function (c) {
    var mine = tasks.filter(function (t) { return t.course === c.id; });
    var open = mine.filter(function (t) { return t.status !== 'done'; });
    var tight = open.filter(function (t) { return isTight(t, sch); }).length;
    var nextT = open.filter(function (t) { return t.due; })[0];

    var meta = [];
    if (c.professor) meta.push(esc(c.professor));
    (c.schedule || []).forEach(function (s) { meta.push(esc(s.day) + ' ' + esc(s.start)); });
    if (c.ends) meta.push('até ' + fmtShort(c.ends));

    var grade = '';
    if (c.grading && c.grading.length) {
      var tot = c.grading.reduce(function (a, g) { return a + (g.weight || 0); }, 0);
      if (tot > 0) {
        grade = '<div class="dc-grade"><div class="wbar">' + c.grading.map(function (g, i) {
          return '<span style="width:' + (100 * (g.weight || 0) / tot).toFixed(2) +
                 '%;background:var(--c-' + esc(c.id) + ');opacity:' + (1 - i * 0.17).toFixed(2) + '"></span>';
        }).join('') + '</div><div class="wleg">' + c.grading.map(function (g) {
          return '<span>' + esc(g.item) + ' <i>' + (g.weight || 0) + '%</i></span>';
        }).join('') + '</div></div>';
      }
    } else {
      grade = '<div class="dc-grade"><div class="wleg"><span>pesos da nota ainda desconhecidos</span></div></div>';
    }

    // Up to five, soonest deadline first; undated fall to the end.
    var top5 = open.slice(0, 5);
    var acts = top5.length ? top5.map(function (t, i) {
      var f = '';
      f += '<div class="act-f"><b>' + esc(countdown(t.days)) + '</b>' +
           (t.due ? '&middot; ' + esc(fmtShort(t.due)) : '') + '</div>';
      f += '<div class="act-f"><b>' + (t.weight == null ? '?' : t.weight + '%') + '</b> da nota</div>';
      if (isTight(t, sch)) {
        f += '<div class="act-f bad">prazo apertado, comece por esta</div>';
      } else if (!t.due) {
        f += '<div class="act-f">sem prazo definido</div>';
      } else {
        f += '<div class="act-f">dá tempo se começar na ordem</div>';
      }
      return '<article class="act">' +
        '<div class="act-top"><span class="act-type">' + esc(TYPES[t.type] || 'Item') + '</span>' +
        '<span class="sz sz-' + esc(t.size) + '">' + esc(SIZE_PT[t.size] || t.size) + '</span>' +
        '<span class="act-idx">' + (i + 1) + '/' + top5.length + '</span></div>' +
        '<div class="act-title">' + esc(t.title) + '</div>' +
        '<div class="act-facts">' + f + '</div>' +
        '<div class="act-foot"><button class="tbtn" data-edit="' + esc(t.id) + '">Editar</button>' +
        '<button class="tbtn" data-toggle="' + esc(t.id) + '">Concluir</button></div>' +
        '</article>';
    }).join('') : '<div class="act-empty">Nenhuma atividade em aberto nesta disciplina.</div>';

    return '<article class="disc-card" style="--c:var(--c-' + esc(c.id) + ');--on-c:var(--on-' + esc(c.id) + ')">' +
      '<div class="dc-head"><div class="dc-top"><span class="dc-tag">' + esc(c.abbr) + '</span>' +
      '<span class="dc-name">' + esc(c.name) + '</span></div>' +
      '<div class="dc-meta">' + meta.join(' &middot; ') + '</div>' +
      '<div class="dc-stats"><span><b>' + open.length + '</b> em aberto</span>' +
      (nextT ? '<span>próxima <b>' + esc(countdown(nextT.days)) + '</b></span>' : '') +
      (tight ? '<span class="dc-tight"><b>' + tight + '</b> com prazo apertado</span>' : '') +
      '</div></div>' + grade + '<div class="dc-sep"></div>' +
      '<div class="acts" id="acts-' + esc(c.id) + '">' + acts + '</div>' +
      '<div class="dots inner" id="dots-' + esc(c.id) + '"></div>' +
      '</article>';
  }).join('');

  wireCarousel('disc', 'discdots', DATA.courses.length, 'discprev', 'discnext');
  DATA.courses.forEach(function (c) {
    var n = document.querySelectorAll('#acts-' + c.id + ' .act').length;
    wireCarousel('acts-' + c.id, 'dots-' + c.id, n);
  });
  wireCardActions(el);
}

/* A tap has to look like it landed. Re-rendering in the same frame made the
   row vanish before the tick was ever drawn, which read as the checkbox not
   working: the item leaves the "Em aberto" filter the instant it is done. So
   paint the finished state on the element first, then re-render once it has
   been on screen long enough to see. */
var HOLD_MS = 620;
function toggleTask(id, btn) {
  var cur = allTasks().filter(function (x) { return x.id === id; })[0];
  var nowDone = !(cur && cur.status === 'done');
  store.override[id] = nowDone ? 'done' : 'todo';
  saveStore();

  var card = btn.closest ? (btn.closest('.item') || btn.closest('.act')) : null;
  if (card) {
    card.classList.toggle('done', nowDone);
    card.classList.add('settling');
    btn.setAttribute('aria-checked', String(nowDone));
    if (btn.classList.contains('tbtn')) btn.textContent = nowDone ? 'Concluída' : 'Concluir';
  }
  clearTimeout(toggleTask._t);
  toggleTask._t = setTimeout(function () {
    render();
    if (modalDay) renderModal();
  }, card ? HOLD_MS : 0);
}

/* Pressed state, so a tap darkens the control straight away. iOS will not
   apply :active reliably without a touch listener on the element. */
function pressFeedback(el) {
  ['pointerdown', 'touchstart'].forEach(function (ev) {
    el.addEventListener(ev, function () { el.classList.add('pressed'); }, { passive: true });
  });
  ['pointerup', 'pointercancel', 'pointerleave', 'touchend', 'touchcancel'].forEach(function (ev) {
    el.addEventListener(ev, function () { el.classList.remove('pressed'); }, { passive: true });
  });
}

/* Buttons live inside both carousels, so the same handlers are wired there. */
function wireCardActions(scope) {
  scope.querySelectorAll('[data-edit]').forEach(function (b) {
    b.addEventListener('click', function (ev) { ev.stopPropagation(); openForm(b.getAttribute('data-edit')); });
  });
  scope.querySelectorAll('[data-toggle]').forEach(function (b) {
    pressFeedback(b);
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      toggleTask(b.getAttribute('data-toggle'), b);
    });
  });
}

/* ---------- upcoming mini carousel ---------- */
function renderUpcoming() {
  var next = allTasks().filter(function (t) { return t.status !== 'done' && t.due != null; }).slice(0, 5);
  var el = document.getElementById('upc');
  if (!next.length) { el.innerHTML = '<div class="mini-card"><div class="mini-title">Nada agendado.</div></div>'; return; }
  el.innerHTML = next.map(function (t) {
    return '<article class="mini-card" style="--c:var(--c-' + esc(t.course) + ')">' +
      '<div class="mini-when">' + esc(countdown(t.days).toUpperCase()) + '</div>' +
      '<div class="mini-title">' + esc(t.title) + '</div>' +
      '<div class="mini-sub">' + esc(t.abbr) + ' &middot; ' + esc(fmtShort(t.due)) +
      ' &middot; ' + esc((SIZE_PT[t.size] || t.size).toLowerCase()) + '</div></article>';
  }).join('');
}

/* Nested horizontal scrollers swallow sideways swipes, so the outer carousel
   also gets tappable dots and arrows, since a swipe inside a discipline's
   activity strip would be the only gesture the page ever sees. */
function wireCarousel(carId, dotId, n, prevId, nextId) {
  var car = document.getElementById(carId), dots = document.getElementById(dotId);
  if (!car || !dots) return;
  if (n <= 1) { dots.innerHTML = ''; }
  else {
    dots.innerHTML = Array.from({ length: n }, function (_, i) {
      return '<button type="button" aria-label="Ir para ' + (i + 1) + '" aria-current="' +
             (i === 0) + '" data-go="' + i + '"><i></i></button>';
    }).join('');
  }
  function stepWidth() {
    var first = car.firstElementChild;
    if (!first) return car.clientWidth;
    var gap = parseFloat(getComputedStyle(car).columnGap || getComputedStyle(car).gap) || 0;
    return first.getBoundingClientRect().width + gap;
  }
  function index() { return Math.min(n - 1, Math.max(0, Math.round(car.scrollLeft / stepWidth()))); }
  function goTo(i) { car.scrollTo({ left: i * stepWidth(), behavior: 'smooth' }); }

  dots.querySelectorAll('[data-go]').forEach(function (b) {
    b.addEventListener('click', function () { goTo(Number(b.getAttribute('data-go'))); });
  });
  var prev = prevId && document.getElementById(prevId);
  var next = nextId && document.getElementById(nextId);
  function sync() {
    var i = index();
    dots.querySelectorAll('[data-go]').forEach(function (b, j) {
      b.setAttribute('aria-current', String(j === i));
    });
    if (prev) prev.disabled = i <= 0;
    if (next) next.disabled = i >= n - 1;
  }
  if (prev) prev.onclick = function () { goTo(Math.max(0, index() - 1)); };
  if (next) next.onclick = function () { goTo(Math.min(n - 1, index() + 1)); };
  car.onscroll = sync;
  sync();
}

/* ---------- focus strip: which discipline each study day belongs to ---------- */
function renderChart(sch) {
  var cells = '', axis = '', counts = [0, 0];
  var tasks = allTasks();
  function byId(id) { return tasks.filter(function (x) { return x.id === id; })[0]; }

  for (var i = 0; i < 14; i++) {
    var day = addDays(TODAY, i);
    var iso = ymd(day);
    var ids = sch.plan[iso] || [];
    var picks = ids.map(byId).filter(Boolean);
    var studyDay = capOf(day) > 0;

    if (picks.length) {
      var bands = picks.map(function (t) {
        return '<i style="background:var(--c-' + esc(t.course) + ')"></i>';
      }).join('');
      cells += '<div class="fcell" style="--on-c:var(--on-' + esc(picks[0].course) + ')" data-tip="' +
               esc(picks.map(function (x) { return x.title; }).join(' + ')) + '">' +
               '<span class="fbands">' + bands + '</span>' +
               '<span class="flab">' + esc(picks.map(function (x) { return x.abbr; }).join('/')) + '</span></div>';
    } else {
      cells += '<div class="fcell empty' + (studyDay ? '' : ' off') + '" data-tip="' +
               (studyDay ? 'livre' : 'sem horário de estudo') + '">' + (studyDay ? '' : '·') + '</div>';
    }

    var dow = day.getDay() === 0 ? 6 : day.getDay() - 1;
    axis += '<div class="pax' + (dow > 4 ? ' wknd' : '') + (i === 0 ? ' today' : '') + '">' +
            '<b>' + DOW[dow][0] + '</b>' + day.getDate() + '</div>';
  }

  // Deliveries per week, counted from real dates rather than any estimate.
  tasks.forEach(function (x) {
    if (x.status === 'done' || x.days == null) return;
    if (x.days >= 0 && x.days < 7) counts[0] += 1;
    else if (x.days >= 7 && x.days < 14) counts[1] += 1;
  });

  document.getElementById('plot').innerHTML = cells;
  document.getElementById('paxis').innerHTML = axis;
  document.getElementById('wktot').innerHTML =
    '<div>Esta semana: <b>' + counts[0] + '</b> entregas</div>' +
    '<div>Semana seguinte: <b>' + counts[1] + '</b> entregas</div>';
  document.getElementById('legend').innerHTML = DATA.courses.map(function (c) {
    return '<span class="lg"><i style="--lc:var(--c-' + esc(c.id) + ')"></i>' + esc(c.abbr) + ': ' + esc(c.name) + '</span>';
  }).join('');
  wireTips();
}

function wireTips() {
  var tip = document.getElementById('tip');
  var plot = document.getElementById('plot');
  plot.querySelectorAll('[data-tip]').forEach(function (seg) {
    function show() {
      tip.textContent = seg.getAttribute('data-tip');
      var pr = plot.getBoundingClientRect(), sr = seg.getBoundingClientRect();
      tip.style.left = Math.max(60, Math.min(pr.width - 60, sr.left - pr.left + sr.width / 2)) + 'px';
      tip.style.top = (sr.top - pr.top - 6) + 'px';
      tip.classList.add('on');
    }
    function hide() { tip.classList.remove('on'); }
    seg.addEventListener('mouseenter', show);
    seg.addEventListener('mouseleave', hide);
    seg.addEventListener('touchstart', show, { passive: true });
    seg.addEventListener('touchend', hide);
  });
}

/* ---------- what to study, day by day ---------- */
function renderDays(sch) {
  var out = '';
  var tasks = allTasks();
  function byId(id) { return tasks.filter(function (x) { return x.id === id; })[0]; }

  for (var i = 0; i < 7; i++) {
    var day = addDays(TODAY, i);
    var iso = ymd(day);
    var dow = day.getDay() === 0 ? 6 : day.getDay() - 1;
    var label = i === 0 ? 'HOJE' : (i === 1 ? 'AMANHÃ' : DOW[dow]);
    var picks = (sch.plan[iso] || []).map(byId).filter(Boolean);
    var errands = classErrands(iso);
    var studyDay = capOf(day) > 0;

    var body = picks.map(function (t) {
      return '<div class="dr-item"><i style="--dc:var(--c-' + esc(t.course) + ')"></i>' +
             '<span>' + esc(t.title) + '</span><em class="dr-tag">' + esc(t.abbr) + '</em></div>' +
             '<div class="dr-why">' + (isTight(t, sch) ? 'prazo apertado' : 'entrega ' + esc(countdown(t.days))) + '</div>';
    }).join('');

    if (!picks.length) {
      body = '<div class="dr-free">' + (studyDay ? 'sem nada pendente' : 'sem horário de estudo') + '</div>';
    }
    errands.forEach(function (t) {
      body += '<div class="dr-errand">na aula: ' + esc(t.title) + '</div>';
    });

    out += '<div class="dayrow' + (studyDay ? '' : ' rest') + '">' +
      '<div class="dr-when"><b>' + label + '</b>' + day.getDate() + '/' + (day.getMonth() + 1) + '</div>' +
      '<div class="dr-items">' + body + '</div></div>';
  }
  document.getElementById('days').innerHTML = out;
}

/* ---------- calendar ---------- */
function renderCal() {
  var byDay = {};
  allTasks().forEach(function (t) {
    if (!t.due || t.status === 'done') return;
    (byDay[t.due] = byDay[t.due] || []).push(t);
  });
  var start = addDays(TODAY, -((TODAY.getDay() + 6) % 7));
  var h = '';
  for (var i = 0; i < 7; i++) h += '<div class="cal-dow">' + DOW[i] + '</div>';
  for (var i = 0; i < 42; i++) {
    var d = addDays(start, i);
    var iso = ymd(d);
    var items = byDay[iso] || [];
    var cls = 'cal-cell';
    if (items.length) cls += ' has';
    // Urgency, not course identity; colour here would be identity by colour alone.
    if (items.some(function (t) { return (t.weight == null ? 0 : t.weight) >= 25; })) cls += ' urg';
    if (iso === TODAY_ISO) cls += ' today';
    if (d < TODAY) cls += ' past';
    if (capOf(d) === 0) cls += ' nostudy';
    var mlab = d.getDate() === 1 ? '<span class="mlab">' + MON[d.getMonth()] + '</span>' : '';
    var cnt = items.length ? '<span class="cnt">' + items.length + '</span>' : '';
    h += '<button class="' + cls + '" data-day="' + iso + '" aria-pressed="' +
         (filter.mode === 'day' && filter.day === iso) + '" aria-label="' + iso + ', ' +
         items.length + ' atividades"><span class="n">' + d.getDate() + '</span>' + mlab + cnt + '</button>';
  }
  var grid = document.getElementById('calgrid');
  grid.innerHTML = h;
  grid.querySelectorAll('[data-day]').forEach(function (b) {
    b.addEventListener('click', function () { openDay(b.getAttribute('data-day')); });
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
  if (!tasks.length) { el.innerHTML = '<p class="empty">Nenhuma atividade neste filtro.</p>'; return; }
  el.innerHTML = tasks.map(function (t) {
    var sub = '<span class="cbadge">' + esc(t.abbr) + '</span><span>' + esc(TYPES[t.type] || 'Item') + '</span>';
    if (t.due) sub += '<span>' + esc(fmtShort(t.due)) + '</span>';
    sub += '<span>' + esc((SIZE_PT[t.size] || t.size).toLowerCase()) + '</span>';
    if (t.weight != null && t.weight > 0) sub += '<span>' + t.weight + '% da nota</span>';
    if (t.mine) sub += '<span class="badge-mine">minha</span>';
    if (t.edited) sub += '<span class="badge-mine">editada</span>';

    var acts = '<div class="it-acts"><button class="tbtn" data-edit="' + esc(t.id) + '">Editar</button>' +
      (t.mine ? '<button class="tbtn danger" data-del="' + esc(t.id) + '">Remover</button>' : '') +
      (t.edited && !t.mine ? '<button class="tbtn" data-reset="' + esc(t.id) + '">Desfazer edição</button>' : '') +
      '</div>';
    var note = (t.notes ? '<p class="it-note">' + esc(t.notes) + '</p>' : '') + renderSteps(t);

    return '<div class="item ' + t.sev + (t.status === 'done' ? ' done' : '') +
      (openIds[t.id] ? ' open' : '') + '" style="--c:var(--c-' + esc(t.course) +
      ');--on-c:var(--on-' + esc(t.course) + ')">' +
      '<div class="it-row">' +
      '<button class="box" data-toggle="' + esc(t.id) + '" role="checkbox" aria-checked="' +
        (t.status === 'done') + '" aria-label="Concluir ' + esc(t.title) + '">' + CHECK + '</button>' +
      '<div class="it-main" data-expand="' + esc(t.id) + '">' +
        '<div class="it-title">' + esc(t.title) + '</div><div class="it-sub">' + sub + '</div></div>' +
      '<span class="pill">' + esc(countdown(t.days)) + '</span></div>' +
      '<div class="it-foot">' + note + acts + '</div></div>';
  }).join('');

  wireCardActions(el);
  wireSteps(el);
  el.querySelectorAll('[data-expand]').forEach(function (b) {
    b.addEventListener('click', function () {
      var id = b.getAttribute('data-expand');
      openIds[id] = !openIds[id]; render();
    });
  });
  el.querySelectorAll('[data-del]').forEach(function (b) {
    b.addEventListener('click', function () {
      var id = b.getAttribute('data-del');
      store.added = store.added.filter(function (t) { return t.id !== id; });
      delete store.override[id]; delete store.edits[id];
      saveStore(); render();
    });
  });
  el.querySelectorAll('[data-reset]').forEach(function (b) {
    b.addEventListener('click', function () {
      delete store.edits[b.getAttribute('data-reset')];
      saveStore(); render();
    });
  });
}

function renderChips() {
  var modes = [['all','Em aberto'],['7','7 dias'],['14','14 dias'],['late','Atrasado'],['done','Concluídas']];
  var h = modes.map(function (m) {
    return '<button class="chip" data-mode="' + m[0] + '" aria-pressed="' + (filter.mode === m[0]) + '">' + m[1] + '</button>';
  }).join('');
  if (filter.mode === 'day') {
    h += '<button class="chip clear" data-mode="all" aria-pressed="false">' + fmtShort(filter.day) + ' &times;</button>';
  }
  var el = document.getElementById('chips');
  el.innerHTML = h;
  el.querySelectorAll('[data-mode]').forEach(function (b) {
    b.addEventListener('click', function () { filter = { mode: b.getAttribute('data-mode'), day: null }; render(); });
  });
}

function renderBanner() {
  var el = document.getElementById('banner');
  if (lsOK) { el.innerHTML = ''; return; }
  el.innerHTML = '<div class="note-box warn">' + WARN +
    '<span>Este navegador não permite salvar alterações no aparelho. Use <b>Exportar</b> antes de fechar, ou me avise pelo chat.</span></div>';
}

/* ---------- form (add + edit) ---------- */
function openForm(id) {
  editingId = id || null;
  var f = document.getElementById('form');
  var t = id ? allTasks().filter(function (x) { return x.id === id; })[0] : null;
  document.getElementById('formtitle').textContent = id ? 'Editar atividade' : 'Nova atividade';
  document.getElementById('f-title').value = t ? t.title : '';
  document.getElementById('f-course').value = t ? t.course : DATA.courses[0].id;
  document.getElementById('f-type').value = t ? t.type : 'assignment';
  document.getElementById('f-due').value = t && t.due ? t.due : TODAY_ISO;
  document.getElementById('f-size').value = t ? (t.size || 'medio') : 'medio';
  document.getElementById('f-weight').value = t && t.weight != null ? t.weight : '';
  f.classList.add('open');
  f.scrollIntoView({ behavior: 'smooth', block: 'center' });
  document.getElementById('f-title').focus();
}
function initForm() {
  document.getElementById('f-course').innerHTML = DATA.courses.map(function (c) {
    return '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>';
  }).join('');
  document.getElementById('addbtn').addEventListener('click', function () { openForm(null); });
  document.getElementById('f-cancel').addEventListener('click', function () {
    document.getElementById('form').classList.remove('open'); editingId = null;
  });
  document.getElementById('form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var title = document.getElementById('f-title').value.trim();
    if (!title) return;
    var wv = document.getElementById('f-weight').value;
    var patch = {
      title: title,
      course: document.getElementById('f-course').value,
      type: document.getElementById('f-type').value,
      due: document.getElementById('f-due').value || null,
      size: document.getElementById('f-size').value,
      weight: wv === '' ? null : Number(wv)
    };
    if (editingId) {
      var isMine = store.added.some(function (t) { return t.id === editingId; });
      if (isMine) {
        store.added = store.added.map(function (t) {
          if (t.id !== editingId) return t;
          var o = {}; for (var k in t) o[k] = t[k];
          for (var k2 in patch) o[k2] = patch[k2];
          return o;
        });
      } else {
        store.edits[editingId] = patch;
      }
    } else {
      patch.id = 'u' + Date.now().toString(36);
      patch.due_time = '';
      patch.status = 'todo';
      patch.notes = '';
      patch.mine = true;
      store.added.push(patch);
    }
    saveStore();
    document.getElementById('form').classList.remove('open');
    editingId = null;
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
      editadas: store.edits,
      passos: store.steps,
      novas: store.added
    };
    var data = JSON.stringify(payload, null, 2);
    var dl = null;
    try { dl = await window.claude.use('downloads'); } catch (e) { dl = null; }
    if (!dl) { showFallback(data); return; }
    try {
      await dl.save({ filename: 'atividades-mestrado.json', data: data });
      btn.textContent = 'Exportado ✓';
      setTimeout(function () { btn.textContent = 'Exportar alterações'; }, 2500);
    } catch (err) {
      if (err && err.code === 'declined') return;
      showFallback(data);
    }
  });
}
function showFallback(data) {
  var box = document.getElementById('fallback');
  box.innerHTML = '<p style="font-size:12.5px;color:var(--muted);margin:8px 0 6px">' +
    'Não foi possível salvar o arquivo. Copie o texto abaixo e cole no chat:</p>' +
    '<textarea readonly style="width:100%;min-height:130px;font-family:var(--mono);font-size:11px;padding:10px;' +
    'border-radius:9px;border:1px solid var(--line);background:var(--bg);color:var(--ink)">' + esc(data) + '</textarea>';
  box.querySelector('textarea').select();
}

/* ---------- steps: the to-do breakdown of one activity ---------- */
function stepState(id) { return store.steps[id] || {}; }
function renderSteps(t) {
  if (!t.steps || !t.steps.length) return '';
  var st = stepState(t.id);
  var done = t.steps.filter(function (_, i) { return st[i]; }).length;
  return '<div class="steps"><div class="steps-h">O que fazer ' +
    '<span class="step-prog">' + done + '/' + t.steps.length + '</span></div>' +
    t.steps.map(function (s, i) {
      return '<button type="button" class="step' + (st[i] ? ' on' : '') + '" data-step="' +
        esc(t.id) + '" data-i="' + i + '" aria-pressed="' + (!!st[i]) + '">' +
        '<i>' + CHECK + '</i><span>' + esc(s) + '</span></button>';
    }).join('') + '</div>';
}
function wireSteps(scope) {
  scope.querySelectorAll('[data-step]').forEach(function (b) {
    pressFeedback(b);
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      var id = b.getAttribute('data-step'), i = b.getAttribute('data-i');
      var st = store.steps[id] || (store.steps[id] = {});
      if (st[i]) delete st[i]; else st[i] = true;
      saveStore();
      render();
      if (modalDay) renderModal();
    });
  });
}

/* ---------- day modal ---------- */
var modalDay = null;
function daysWithActivities() {
  var set = {};
  allTasks().forEach(function (t) { if (t.due && t.status !== 'done') set[t.due] = true; });
  return Object.keys(set).sort();
}
function openDay(iso) { modalDay = iso; renderModal(); document.getElementById('scrim').classList.add('on'); }
function closeDay() {
  modalDay = null;
  document.getElementById('scrim').classList.remove('on');
  renderCal();
}
function stepDay(dir) {
  var list = daysWithActivities();
  if (!list.length) return;
  // Move to the next/previous day that actually has something on it.
  var i = list.indexOf(modalDay);
  if (i === -1) {
    for (var k = 0; k < list.length; k++) {
      if (dir > 0 && list[k] > modalDay) { i = k; modalDay = list[k]; renderModal(); return; }
      if (dir < 0 && list[k] < modalDay) { i = k; }
    }
    if (dir < 0 && i !== -1) { modalDay = list[i]; renderModal(); }
    return;
  }
  var j = i + dir;
  if (j < 0 || j >= list.length) return;
  modalDay = list[j];
  renderModal();
}
function renderModal() {
  if (!modalDay) return;
  var items = allTasks().filter(function (t) { return t.due === modalDay; });
  var d = parseISO(modalDay);
  document.getElementById('mdtitle').textContent =
    FULLDOW[d.getDay() === 0 ? 6 : d.getDay() - 1] + ', ' + d.getDate() + ' de ' + FULLMON[d.getMonth()];
  var open = items.filter(function (t) { return t.status !== 'done'; }).length;
  document.getElementById('mdsub').textContent =
    open === 0 ? 'nada em aberto' : (open === 1 ? '1 atividade' : open + ' atividades');

  var body = document.getElementById('mdbody');
  body.innerHTML = items.length ? items.map(function (t) {
    return '<div class="item ' + t.sev + (t.status === 'done' ? ' done' : '') +
      (openIds[t.id] ? ' open' : '') + '" ' +
      'style="--c:var(--c-' + esc(t.course) + ');--on-c:var(--on-' + esc(t.course) + ')">' +
      '<div class="it-row">' +
      '<button class="box" data-toggle="' + esc(t.id) + '" role="checkbox" aria-checked="' +
        (t.status === 'done') + '" aria-label="Concluir">' + CHECK + '</button>' +
      '<div class="it-main" data-expand="' + esc(t.id) + '"><div class="it-title">' + esc(t.title) + '</div>' +
      '<div class="it-sub"><span class="cbadge">' + esc(t.abbr) + '</span>' +
      '<span>' + esc(TYPES[t.type] || '') + '</span>' +
      '<span>' + esc((SIZE_PT[t.size] || t.size).toLowerCase()) + '</span>' +
      (t.weight != null && t.weight > 0 ? '<span>' + t.weight + '% da nota</span>' : '') +
      '</div></div><span class="pill">' + esc(countdown(t.days)) + '</span></div>' +
      (t.steps && t.steps.length && !openIds[t.id]
        ? '<div class="it-peek">toque para ver o que fazer</div>' : '') +
      '<div class="it-foot">' + renderSteps(t) +
      '<div class="it-acts"><button class="tbtn" data-edit="' + esc(t.id) + '">Editar</button></div>' +
      '</div></div>';
  }).join('') : '<p class="empty">Nada marcado para este dia.</p>';

  wireCardActions(body);
  wireSteps(body);
  body.querySelectorAll('[data-expand]').forEach(function (b) {
    b.addEventListener('click', function () {
      var id = b.getAttribute('data-expand');
      openIds[id] = !openIds[id];
      renderModal();
    });
  });

  var list = daysWithActivities();
  var i = list.indexOf(modalDay);
  document.getElementById('mdprev').disabled = !(i > 0 || (i === -1 && list.some(function (x) { return x < modalDay; })));
  document.getElementById('mdnext').disabled = !((i > -1 && i < list.length - 1) || (i === -1 && list.some(function (x) { return x > modalDay; })));
}
function initModal() {
  document.getElementById('mdclose').addEventListener('click', closeDay);
  document.getElementById('scrim').addEventListener('click', function (ev) {
    if (ev.target.id === 'scrim') closeDay();
  });
  document.getElementById('mdprev').addEventListener('click', function () { stepDay(-1); });
  document.getElementById('mdnext').addEventListener('click', function () { stepDay(1); });
  document.addEventListener('keydown', function (ev) {
    if (!modalDay) return;
    if (ev.key === 'Escape') closeDay();
    if (ev.key === 'ArrowLeft') stepDay(-1);
    if (ev.key === 'ArrowRight') stepDay(1);
  });
  // Horizontal drag anywhere in the sheet jumps to the next/previous busy day.
  var x0 = null, y0 = null;
  var sheet = document.getElementById('daymodal');
  sheet.addEventListener('touchstart', function (ev) {
    x0 = ev.touches[0].clientX; y0 = ev.touches[0].clientY;
  }, { passive: true });
  sheet.addEventListener('touchend', function (ev) {
    if (x0 == null) return;
    var dx = ev.changedTouches[0].clientX - x0, dy = ev.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.6) stepDay(dx < 0 ? 1 : -1);
    x0 = y0 = null;
  });
}

/* ---------- boot ---------- */
function renderHeading() {
  var d = TODAY;
  document.getElementById('hoje').textContent =
    FULLDOW[d.getDay() === 0 ? 6 : d.getDay() - 1] + ', ' + d.getDate() + ' de ' + FULLMON[d.getMonth()];
  document.getElementById('rel').textContent =
    'Contagens relativas a ' + String(d.getDate()).padStart(2, '0') + '/' +
    String(d.getMonth() + 1).padStart(2, '0') + '/' + d.getFullYear() + ' em ' + DATA.tz + '.';
}

/* Anything changed here lives only on this device until it is exported, so the
   page says how much is waiting rather than letting it pile up unnoticed. */
function pendingCount() {
  var n = Object.keys(store.override).length + Object.keys(store.edits).length + store.added.length;
  Object.keys(store.steps).forEach(function (k) { n += Object.keys(store.steps[k]).length; });
  return n;
}
function renderPending() {
  var el = document.getElementById('pending');
  var n = pendingCount();
  if (!n) { el.innerHTML = ''; return; }
  el.innerHTML = '<div class="pend">' +
    '<span>' + n + (n === 1 ? ' alteração guardada neste aparelho' : ' alterações guardadas neste aparelho') +
    '</span><button class="tbtn" id="pendexport">Exportar</button></div>';
  document.getElementById('pendexport').addEventListener('click', function () {
    document.getElementById('exportbtn').click();
    document.getElementById('exportbtn').scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}

function render() {
  var sch = schedule();
  renderHeading();
  renderPending();
  renderBrief(sch);
  renderDisciplines(sch);
  renderUpcoming();
  renderChart(sch);
  renderDays(sch);
  renderCal();
  renderChips();
  renderList();
  renderBanner();
}
loadStore();
initForm();
initModal();
initExport();
render();
"""


# --------------------------------------------------------------------------
# server-rendered fragments
# --------------------------------------------------------------------------

def color_tokens(courses: list[dict]) -> str:
    def block(key, indent="  "):
        out = ""
        for c in courses:
            col = c.get(key) or c.get("color") or "#888"
            out += f"{indent}--c-{c.get('id')}: {col};\n"
            out += f"{indent}--on-{c.get('id')}: {ink_on(col)};\n"
        return out
    light, dark = block("color"), block("color_dark")
    return (
        f":root {{\n{light}  --c-none: #868D9B;\n  --on-none: #ffffff;\n}}\n"
        f"@media (prefers-color-scheme: dark) {{\n :root:not([data-theme=\"light\"]) {{\n{block('color_dark',' ')} }}\n}}\n"
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
            cid = course.get("id")
            blocks += (
                f'<div class="blk" style="--c:var(--c-{cid});--on-c:var(--on-{cid});'
                f'top:{100 * (s - TIMETABLE_START) / span:.3f}%;'
                f'height:{100 * (e - s) / span:.3f}%;'
                f'left:{lane * w:.3f}%;width:{w:.3f}%">'
                f'<b>{esc(slot.get("start"))}</b>{esc(course.get("abbr") or course.get("name"))}</div>'
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

    return (f'<section class="px"><h2>Semana de aulas</h2><div class="tt-wrap">'
            f'<div class="tt">{heads}{cols}</div>{note}</div></section>')


def payload(m: dict) -> str:
    return json.dumps({
        "today": m["today"].isoformat(),
        "tz": m["tz"],
        "capacity": m["capacity"],
        "courses": [{
            "id": c.get("id"), "name": c.get("name"), "abbr": c.get("abbr"),
            "professor": c.get("professor") or "",
            "ends": as_date(c.get("ends")).isoformat() if as_date(c.get("ends")) else None,
            "schedule": [{"day": DAY_PT.get((s.get("day") or "").lower(), ""),
                          "dayKey": (s.get("day") or "").lower(),
                          "start": s.get("start"), "end": s.get("end"),
                          "where": s.get("where") or ""}
                         for s in (c.get("schedule") or [])],
            "grading": [{"item": g.get("item"), "weight": g.get("weight") or 0}
                        for g in (c.get("grading") or [])],
        } for c in m["courses"]],
        "tasks": m["tasks"],
        "sizeDays": SIZE_DAYS,
    }, ensure_ascii=False, separators=(",", ":"))


def render_html(m: dict) -> str:
    today = m["today"]
    heading = f"{FULLDAY_PT[today.weekday()]}, {today.day} de {FULLMONTH_PT[today.month - 1]}"
    types = "".join(f'<option value="{k}">{v}</option>' for k, v in TYPE_PT.items())

    return f"""<title>Painel do Mestrado</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#F4F5F7">
<style>{CSS}{color_tokens(m['courses'])}</style>
<div class="page">
  <header class="px">
    <div class="term">{esc(m['term'])} &middot; UFSC &middot; 5 disciplinas</div>
    <h1 id="hoje">{heading}</h1>
  </header>

  <div class="px" id="banner"></div>
  <div class="px" id="pending"></div>
  <div class="px" id="brief"></div>

  <section>
    <h2 class="px">Disciplinas <span class="sub">deslize para trocar; dentro de cada uma, as 5 próximas</span></h2>
    <div class="carousel" id="disc"></div>
    <div class="carnav">
      <button class="arrow" id="discprev" aria-label="Disciplina anterior">&#8249;</button>
      <div class="dots" id="discdots"></div>
      <button class="arrow" id="discnext" aria-label="Próxima disciplina">&#8250;</button>
    </div>
  </section>

  <section>
    <h2 class="px">Próximas 5 entregas</h2>
    <div class="carousel" id="upc"></div>
  </section>

  <section class="px">
    <h2>Plano de estudo <span class="sub">pelo prazo mais próximo</span></h2>
    <div class="chart-card">
      <div class="legend" id="legend"></div>
      <div style="position:relative">
        <div class="plot" id="plot"></div>
        <div class="tip" id="tip"></div>
      </div>
      <div class="paxis" id="paxis"></div>
      <div class="wk-tot" id="wktot"></div>
    </div>
    <div class="days" id="days"></div>
  </section>

  <section class="px">
    <h2>Calendário</h2>
    <div class="cal">
      <div class="cal-grid" id="calgrid"></div>
      <div class="cal-legend">
        O número no canto é quantas atividades vencem no dia &middot; fundo vermelho = tem item
        de peso alto &middot; dia <span style="text-decoration:underline dotted;text-underline-offset:3px">sublinhado</span>
        = sem horário de estudo. Toque para abrir o dia.
      </div>
    </div>
  </section>

  <section class="px">
    <h2>Atividades</h2>
    <div class="chips" id="chips"></div>
    <div class="list" id="lista"></div>

    <button class="add-btn" id="addbtn">+ Nova atividade</button>
    <form class="form" id="form">
      <div class="form-title" id="formtitle">Nova atividade</div>
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
          <label for="f-size">Tamanho</label>
          <select id="f-size">
            <option value="pequeno">Pequeno</option>
            <option value="medio" selected>Médio</option>
            <option value="grande">Grande</option>
          </select>
        </div>
      </div>
      <div class="form-2">
        <div class="field">
          <label for="f-type">Tipo</label>
          <select id="f-type">{types}</select>
        </div>
        <div class="field">
          <label for="f-weight">% da nota</label>
          <input id="f-weight" type="number" min="0" max="100" step="1" placeholder="opcional">
        </div>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn primary">Salvar</button>
        <button type="button" class="btn" id="f-cancel">Cancelar</button>
      </div>
    </form>
  </section>

  {render_timetable(m)}

  <div class="scrim" id="scrim" role="dialog" aria-modal="true" aria-labelledby="mdtitle">
    <div class="modal" id="daymodal">
      <div class="md-head">
        <button class="md-nav" id="mdprev" aria-label="Dia anterior com atividades">&#8249;</button>
        <div class="md-title"><b id="mdtitle"></b><span id="mdsub"></span></div>
        <button class="md-nav" id="mdnext" aria-label="Próximo dia com atividades">&#8250;</button>
        <button class="md-x" id="mdclose" aria-label="Fechar">&times;</button>
      </div>
      <div class="md-body" id="mdbody"></div>
      <div class="md-hint">arraste para o lado para trocar de dia</div>
    </div>
  </div>

  <footer class="px">
    <button class="btn" id="exportbtn">Exportar alterações</button>
    <div id="fallback"></div>
    O que você marca, edita e adiciona aqui fica salvo <b>neste aparelho</b>. Para gravar
    no repositório de vez, exporte e me envie o arquivo no chat.<br>
<span id="rel"></span>
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
