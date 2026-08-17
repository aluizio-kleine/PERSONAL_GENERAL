#!/usr/bin/env python3
"""Build the term dashboard from courses.yml + tasks.yml.

Usage:
    python3 study/build_dashboard.py            # writes study/dashboard.html
    python3 study/build_dashboard.py --brief    # prints the plain-text daily brief

The page renders client-side from a baked JSON payload: it schedules the work
into the study hours declared in courses.yml, ranks what is critical, and lets
the viewer complete, edit and add activities. Those edits live in the viewer's
device storage; the YAML files stay the source of truth and are reconciled from
the page's export file.
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
            "effort": raw.get("effort") or 0,
            "weight": raw.get("weight"),
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

    cap_today = m["capacity"][DAY_KEYS[today.weekday()]]
    lines += ["", f"Horas de estudo disponíveis hoje: {cap_today}h"]

    if next7:
        lines += ["", f"Nos próximos 7 dias ({h7}h de trabalho):"]
        lines += [f"  - {countdown(t['days']):>12}  {t['title']} [{t['course_name']}]" for t in next7]
    else:
        lines += ["", "Nada nos próximos 7 dias."]

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
  display: flex; gap: 10px; scroll-snap-type: x mandatory; scrollbar-width: none;
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
.acts { display: flex; gap: 8px; scroll-snap-type: x mandatory; scrollbar-width: none;
        overflow-x: auto; overflow-y: hidden; width: 100%; max-width: 100%; min-width: 0;
        padding: 0 16px 2px; overscroll-behavior-x: contain; }
.acts::-webkit-scrollbar { display: none; }
.act {
  flex: 0 0 calc(100% - 26px); scroll-snap-align: center; min-width: 0;
  background: var(--bg); border: 1px solid var(--line); border-radius: 11px;
  padding: 12px 13px; display: flex; flex-direction: column; gap: 8px;
}
.act-top { display: flex; align-items: center; gap: 8px; }
.act-type { font-size: 11px; font-weight: 650; color: var(--muted); }
.act-idx { font-family: var(--mono); font-size: 10px; font-weight: 700; color: var(--faint); margin-left: auto; }
.act-title { font-size: 14.5px; font-weight: 600; line-height: 1.3; text-wrap: pretty; }
.act-facts { display: flex; flex-direction: column; gap: 4px; }
.act-f { display: flex; align-items: baseline; gap: 6px; font-size: 12.5px; color: var(--muted); }
.act-f b { font-family: var(--mono); font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; }
.act-f.bad, .act-f.bad b { color: var(--danger); }
.act-f .est { font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
              color: var(--faint); border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; }
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
.plot { position: relative; display: grid; grid-template-columns: repeat(14, 1fr); gap: 3px; height: 128px; align-items: end; }
.pcol { position: relative; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; cursor: default; }
.ptrack { position: absolute; left: 0; right: 0; bottom: 0; background: var(--sunken); border-radius: 3px; }
.pstack { position: relative; display: flex; flex-direction: column-reverse; }
.pseg { display: block; background: var(--sc); margin-top: 2px; }
.pstack > .pseg:last-child { border-radius: 4px 4px 0 0; }
.pcol.today .ptrack { outline: 2px solid var(--ink); outline-offset: 1px; }
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
       background: var(--card); cursor: pointer; display: grid; place-items: center; padding: 0; color: transparent; }
.box:hover { border-color: var(--muted); }
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

.note-box { display: flex; gap: 9px; align-items: flex-start; border-radius: 10px; padding: 11px 13px; font-size: 13.5px; font-weight: 500; }
.note-box.bad { background: var(--danger-soft); color: var(--danger); }
.note-box.warn { background: var(--warn-soft); color: var(--warn); }
.note-box svg { flex: none; margin-top: 2px; }

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
var store = { override: {}, edits: {}, added: [], version: 2 };
var lsOK = true;
var filter = { mode: 'all', day: null };
var openIds = {};
var editingId = null;
var DEFAULT_WEIGHT = 15;

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

/* --------------------------------------------------------------------
   Scheduler: earliest deadline first, poured into each day's real study
   hours. This is what turns a pile of deadlines into "today you do 2h of
   X and 1h of Y", and what reveals work that cannot fit before its due
   date no matter how the days are arranged.
   -------------------------------------------------------------------- */
var HORIZON = 140;
function schedule() {
  var queue = allTasks().filter(function (t) {
    return t.status !== 'done' && (t.effort || 0) > 0 && t.due;
  }).sort(function (a, b) {
    if (a.due !== b.due) return a.due < b.due ? -1 : 1;
    return (b.weight == null ? DEFAULT_WEIGHT : b.weight) - (a.weight == null ? DEFAULT_WEIGHT : a.weight);
  });

  var left = {};
  queue.forEach(function (t) { left[t.id] = t.effort; });

  var plan = {};                      // iso -> [{id, hours}]
  var doneBy = {};                    // id -> hours allocated on/before its due date
  queue.forEach(function (t) { doneBy[t.id] = 0; });

  for (var i = 0; i < HORIZON; i++) {
    var day = addDays(TODAY, i);
    var iso = ymd(day);
    var cap = capOf(day);
    if (cap <= 0) continue;
    var slots = [];
    for (var j = 0; j < queue.length && cap > 0; j++) {
      var t = queue[j];
      if (left[t.id] <= 0) continue;
      var take = Math.min(cap, left[t.id]);
      left[t.id] -= take;
      cap -= take;
      slots.push({ id: t.id, hours: take });
      if (iso <= t.due) doneBy[t.id] += take;
    }
    if (slots.length) plan[iso] = slots;
  }
  return { plan: plan, doneBy: doneBy, left: left };
}

/* ---------- outer carousel: disciplines, each holding its own activity carousel
   Order inside a discipline is simply by deadline — no invented score. The one
   judgement shown is factual and comes from the scheduler: whether the hours
   still fit before the date. ---------- */
function renderDisciplines(sch) {
  var tasks = allTasks();
  var el = document.getElementById('disc');

  el.innerHTML = DATA.courses.map(function (c) {
    var mine = tasks.filter(function (t) { return t.course === c.id; });
    var open = mine.filter(function (t) { return t.status !== 'done'; });
    var hours = open.reduce(function (a, t) { return a + (t.effort || 0); }, 0);
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
      var fitted = t.due ? (sch.doneBy[t.id] || 0) : null;
      var gap = fitted == null ? 0 : Math.max(0, (t.effort || 0) - fitted);
      var f = '';
      f += '<div class="act-f"><b>' + esc(countdown(t.days)) + '</b>' +
           (t.due ? '&middot; ' + esc(fmtShort(t.due)) : '') + '</div>';
      f += '<div class="act-f"><b>' + (t.effort || 0) + 'h</b> previstas ' +
           '<span class="est" title="estimativa minha, não do plano de ensino">est.</span></div>';
      f += '<div class="act-f"><b>' + (t.weight == null ? '?' : t.weight + '%') + '</b> da nota</div>';
      if (gap > 0) {
        f += '<div class="act-f bad">cabem <b>' + fitted + 'h</b> antes do prazo, faltam <b>' + gap + 'h</b></div>';
      } else if (t.due && t.effort) {
        f += '<div class="act-f">cabe nas horas disponíveis</div>';
      }
      return '<article class="act">' +
        '<div class="act-top"><span class="act-type">' + esc(TYPES[t.type] || 'Item') + '</span>' +
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
      '<span><b>' + hours + 'h</b> previstas</span>' +
      (nextT ? '<span>próxima <b>' + esc(countdown(nextT.days)) + '</b></span>' : '') +
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

/* Buttons live inside both carousels, so the same handlers are wired there. */
function wireCardActions(scope) {
  scope.querySelectorAll('[data-edit]').forEach(function (b) {
    b.addEventListener('click', function (ev) { ev.stopPropagation(); openForm(b.getAttribute('data-edit')); });
  });
  scope.querySelectorAll('[data-toggle]').forEach(function (b) {
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      var id = b.getAttribute('data-toggle');
      var cur = allTasks().filter(function (x) { return x.id === id; })[0];
      store.override[id] = (cur && cur.status === 'done') ? 'todo' : 'done';
      saveStore(); render();
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
      (t.effort ? ' &middot; ' + t.effort + 'h' : '') + '</div></article>';
  }).join('');
}

/* Nested horizontal scrollers swallow sideways swipes, so the outer carousel
   also gets tappable dots and arrows — otherwise a swipe inside a discipline's
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

/* ---------- plan chart ---------- */
function renderChart(sch) {
  var maxCap = Math.max.apply(null, DAYK.map(function (k) { return DATA.capacity[k] || 0; }).concat([1]));
  var cols = '', axis = '', totals = [0, 0];

  for (var i = 0; i < 14; i++) {
    var day = addDays(TODAY, i);
    var iso = ymd(day);
    var cap = capOf(day);
    var slots = sch.plan[iso] || [];
    var used = slots.reduce(function (a, s) { return a + s.hours; }, 0);
    totals[i < 7 ? 0 : 1] += used;

    var segs = slots.map(function (s) {
      var t = allTasks().filter(function (x) { return x.id === s.id; })[0] || {};
      return '<i class="pseg" style="--sc:var(--c-' + esc(t.course) + ');height:' +
             (100 * s.hours / maxCap).toFixed(2) + '%" data-tip="' +
             esc(s.hours + 'h · ' + (t.title || '')) + '"></i>';
    }).join('');

    cols += '<div class="pcol' + (i === 0 ? ' today' : '') + '">' +
      '<div class="ptrack" style="height:' + (100 * cap / maxCap).toFixed(2) + '%"></div>' +
      '<div class="pstack" style="height:' + (100 * used / maxCap).toFixed(2) + '%">' + segs + '</div></div>';

    var wknd = (day.getDay() === 0 || day.getDay() === 6);
    axis += '<div class="pax' + (wknd ? ' wknd' : '') + (i === 0 ? ' today' : '') + '">' +
            '<b>' + DOW[day.getDay() === 0 ? 6 : day.getDay() - 1][0] + '</b>' + day.getDate() + '</div>';
  }

  document.getElementById('plot').innerHTML = cols;
  document.getElementById('paxis').innerHTML = axis;
  var cap0 = 0, cap1 = 0;
  for (var j = 0; j < 14; j++) { var c = capOf(addDays(TODAY, j)); if (j < 7) cap0 += c; else cap1 += c; }
  document.getElementById('wktot').innerHTML =
    '<div>Semana 1: <b>' + totals[0] + 'h</b> de <b>' + cap0 + 'h</b></div>' +
    '<div>Semana 2: <b>' + totals[1] + 'h</b> de <b>' + cap1 + 'h</b></div>';

  document.getElementById('legend').innerHTML = DATA.courses.map(function (c) {
    return '<span class="lg"><i style="--lc:var(--c-' + esc(c.id) + ')"></i>' + esc(c.abbr) + ' — ' + esc(c.name) + '</span>';
  }).join('');

  wireTips();
}

function wireTips() {
  var tip = document.getElementById('tip');
  var plot = document.getElementById('plot');
  plot.querySelectorAll('[data-tip]').forEach(function (seg) {
    function show(ev) {
      tip.textContent = seg.getAttribute('data-tip');
      var pr = plot.getBoundingClientRect(), sr = seg.getBoundingClientRect();
      tip.style.left = (sr.left - pr.left + sr.width / 2) + 'px';
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

/* ---------- per-day plan ---------- */
function renderDays(sch) {
  var out = '';
  for (var i = 0; i < 7; i++) {
    var day = addDays(TODAY, i);
    var iso = ymd(day);
    var cap = capOf(day);
    var slots = sch.plan[iso] || [];
    var label = i === 0 ? 'HOJE' : (i === 1 ? 'AMANHÃ' : DOW[day.getDay() === 0 ? 6 : day.getDay() - 1]);
    var items = slots.length ? slots.map(function (s) {
      var t = allTasks().filter(function (x) { return x.id === s.id; })[0] || {};
      return '<div class="dr-item"><i style="--dc:var(--c-' + esc(t.course) + ')"></i>' +
             '<span>' + esc(t.title) + '</span><b>' + s.hours + 'h</b></div>';
    }).join('') : '<div class="dr-free">' + (cap ? cap + 'h livres' : 'sem horário de estudo') + '</div>';
    out += '<div class="dayrow' + (cap ? '' : ' rest') + '">' +
      '<div class="dr-when"><b>' + label + '</b>' + day.getDate() + '/' + (day.getMonth()+1) + '</div>' +
      '<div class="dr-items">' + items + '</div></div>';
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
    // Urgency, not course identity — colour here would be identity by colour alone.
    if (items.some(function (t) { return (t.weight == null ? 0 : t.weight) >= 25; })) cls += ' urg';
    if (iso === DATA.today) cls += ' today';
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
    b.addEventListener('click', function () {
      var iso = b.getAttribute('data-day');
      filter = (filter.mode === 'day' && filter.day === iso) ? { mode: 'all', day: null } : { mode: 'day', day: iso };
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
  if (!tasks.length) { el.innerHTML = '<p class="empty">Nenhuma atividade neste filtro.</p>'; return; }
  el.innerHTML = tasks.map(function (t) {
    var sub = '<span class="cbadge">' + esc(t.abbr) + '</span><span>' + esc(TYPES[t.type] || 'Item') + '</span>';
    if (t.due) sub += '<span>' + esc(fmtShort(t.due)) + '</span>';
    if (t.effort) sub += '<span>' + t.effort + 'h</span>';
    if (t.weight != null && t.weight > 0) sub += '<span>' + t.weight + '% da nota</span>';
    if (t.mine) sub += '<span class="badge-mine">minha</span>';
    if (t.edited) sub += '<span class="badge-mine">editada</span>';

    var acts = '<div class="it-acts"><button class="tbtn" data-edit="' + esc(t.id) + '">Editar</button>' +
      (t.mine ? '<button class="tbtn danger" data-del="' + esc(t.id) + '">Remover</button>' : '') +
      (t.edited && !t.mine ? '<button class="tbtn" data-reset="' + esc(t.id) + '">Desfazer edição</button>' : '') +
      '</div>';
    var note = t.notes ? '<p class="it-note">' + esc(t.notes) + '</p>' : '';

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
  document.getElementById('f-due').value = t && t.due ? t.due : DATA.today;
  document.getElementById('f-effort').value = t ? (t.effort || 0) : 2;
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
      effort: Number(document.getElementById('f-effort').value) || 0,
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

/* ---------- boot ---------- */
function render() {
  var sch = schedule();
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
        "capacity": m["capacity"],
        "courses": [{
            "id": c.get("id"), "name": c.get("name"), "abbr": c.get("abbr"),
            "professor": c.get("professor") or "",
            "ends": as_date(c.get("ends")).isoformat() if as_date(c.get("ends")) else None,
            "schedule": [{"day": DAY_PT.get((s.get("day") or "").lower(), ""), "start": s.get("start")}
                         for s in (c.get("schedule") or [])],
            "grading": [{"item": g.get("item"), "weight": g.get("weight") or 0}
                        for g in (c.get("grading") or [])],
        } for c in m["courses"]],
        "tasks": m["tasks"],
    }, ensure_ascii=False, separators=(",", ":"))


def render_html(m: dict) -> str:
    today = m["today"]
    heading = f"{FULLDAY_PT[today.weekday()]}, {today.day} de {FULLMONTH_PT[today.month - 1]}"
    types = "".join(f'<option value="{k}">{v}</option>' for k, v in TYPE_PT.items())
    week_cap = sum(m["capacity"].values())

    return f"""<title>Painel do Mestrado</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#F4F5F7">
<style>{CSS}{color_tokens(m['courses'])}</style>
<div class="page">
  <header class="px">
    <div class="term">{esc(m['term'])} &middot; UFSC &middot; 5 disciplinas</div>
    <h1>{heading}</h1>
  </header>

  <div class="px" id="banner"></div>

  <section>
    <h2 class="px">Disciplinas <span class="sub">— deslize para trocar; dentro de cada uma, as 5 próximas</span></h2>
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
    <h2>Plano de estudo <span class="sub">— {week_cap}h por semana disponíveis</span></h2>
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
        = sem horário de estudo. Toque para filtrar a lista.
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
          <label for="f-effort">Horas</label>
          <input id="f-effort" type="number" min="0" max="99" step="1" value="2">
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

  <footer class="px">
    <button class="btn" id="exportbtn">Exportar alterações</button>
    <div id="fallback"></div>
    O que você marca, edita e adiciona aqui fica salvo <b>neste aparelho</b>. Para gravar
    no repositório de vez, exporte e me envie o arquivo no chat.<br>
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
