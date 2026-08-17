#!/usr/bin/env python3
"""Build the term dashboard from courses.yml + tasks.yml.

Usage:
    python3 study/build_dashboard.py            # writes study/dashboard.html
    python3 study/build_dashboard.py --brief    # prints the plain-text daily brief
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
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
TYPE_ICON = {
    "assignment": "M4 4h10l4 4v12H4z M14 4v4h4",
    "exam": "M5 3h14v18l-7-4-7 4z",
    "reading": "M3 5h8v15H3z M13 5h8v15h-8z",
    "paper": "M6 3h9l4 4v14H6z M6 11h12 M6 15h12",
    "presentation": "M3 4h18v11H3z M12 15v5 M8 20h8",
    "admin": "M12 3a9 9 0 100 18 9 9 0 000-18z M12 8v5 M12 16v.5",
}

TIMETABLE_START = 8 * 60      # 08:00
TIMETABLE_END = 21 * 60       # 21:00


# --------------------------------------------------------------------------
# loading + helpers
# --------------------------------------------------------------------------

def load() -> tuple[dict, dict]:
    courses = yaml.safe_load((HERE / "courses.yml").read_text(encoding="utf-8")) or {}
    tasks = yaml.safe_load((HERE / "tasks.yml").read_text(encoding="utf-8")) or {}
    return courses, tasks


def today_in(tzname: str) -> dt.date:
    """Local date in the student's timezone, falling back to UTC-3 if the
    system has no tz database (slim containers often don't)."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tzname)).date()
    except Exception:
        return (dt.datetime.utcnow() - dt.timedelta(hours=3)).date()


def minutes(hhmm) -> int:
    """'13:30' -> 810. Unparseable or missing times sort to 0."""
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


def severity(days: int | None, status: str) -> str:
    if status == "done":
        return "done"
    if days is None:
        return "calm"
    if days < 0:
        return "late"
    if days == 0:
        return "now"
    if days <= 3:
        return "soon"
    if days <= 7:
        return "week"
    return "calm"


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
# derived model
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
    capacity = courses_doc.get("weekly_capacity") or 20

    tasks = []
    for raw in (tasks_doc.get("tasks") or []):
        due = as_date(raw.get("due"))
        days = (due - today).days if due else None
        status = (raw.get("status") or "todo").lower()
        course = by_id.get(raw.get("course")) or {}
        tasks.append({
            "id": raw.get("id"),
            "title": raw.get("title") or "(sem título)",
            "type": (raw.get("type") or "assignment").lower(),
            "course_name": course.get("name", "Sem disciplina"),
            "course_id": raw.get("course") or "none",
            "due": due,
            "due_time": raw.get("due_time") or "",
            "days": days,
            "effort": raw.get("effort") or 0,
            "status": status,
            "notes": (raw.get("notes") or "").strip(),
            "sev": severity(days, status),
        })

    open_tasks = [t for t in tasks if t["status"] != "done"]
    open_tasks.sort(key=lambda t: (t["days"] is None, t["days"] if t["days"] is not None else 0))
    done_tasks = [t for t in tasks if t["status"] == "done"]

    todays_key = DAY_KEYS[today.weekday()]
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

    # Six weekly buckets starting this Monday — the horizon that matters.
    monday = today - dt.timedelta(days=today.weekday())
    buckets = []
    for i in range(6):
        start = monday + dt.timedelta(days=7 * i)
        end = start + dt.timedelta(days=6)
        items = [t for t in open_tasks if t["due"] and start <= t["due"] <= end]
        buckets.append({
            "start": start, "end": end, "items": items,
            "hours": sum(t["effort"] for t in items),
            "is_current": i == 0,
        })

    horizon7 = [t for t in open_tasks if t["days"] is not None and 0 <= t["days"] <= 7]
    horizon14 = [t for t in open_tasks if t["days"] is not None and 0 <= t["days"] <= 14]
    late = [t for t in open_tasks if t["days"] is not None and t["days"] < 0]

    return {
        "today": today, "tz": tz, "term": courses_doc.get("term") or "",
        "capacity": capacity, "courses": courses,
        "tasks": tasks, "open": open_tasks, "done": done_tasks,
        "todays_classes": week[todays_key],
        "todays_tasks": [t for t in open_tasks if t["days"] == 0],
        "week": week, "clashes": clashes, "buckets": buckets,
        "late": late,
        "next7": horizon7, "hours7": sum(t["effort"] for t in horizon7),
        "next14": horizon14, "hours14": sum(t["effort"] for t in horizon14),
        "next_up": open_tasks[0] if open_tasks else None,
    }


# --------------------------------------------------------------------------
# plain-text brief (used by the scheduled morning push)
# --------------------------------------------------------------------------

def brief(m: dict) -> str:
    lines = [f"{FULLDAY_PT[m['today'].weekday()]}, {m['today'].day} de {FULLMONTH_PT[m['today'].month - 1]}"]

    if m["late"]:
        lines.append("")
        lines.append(f"ATRASADO ({len(m['late'])}):")
        for t in m["late"]:
            lines.append(f"  - {t['title']} [{t['course_name']}] {countdown(t['days'])}")

    if m["todays_classes"]:
        lines.append("")
        lines.append("Aulas hoje:")
        for item in m["todays_classes"]:
            slot = item["slot"]
            where = slot.get("where") or ""
            lines.append(f"  - {slot.get('start','')}-{slot.get('end','')} {item['course']['name']}"
                         + (f" ({where})" if where else ""))
    else:
        lines.append("")
        lines.append("Sem aulas hoje.")

    if m["next7"]:
        lines.append("")
        lines.append(f"Nos próximos 7 dias ({m['hours7']}h de trabalho):")
        for t in m["next7"]:
            lines.append(f"  - {countdown(t['days']):>12}  {t['title']} [{t['course_name']}]")
    else:
        lines.append("")
        lines.append("Nada nos próximos 7 dias.")

    # The 7-day figure hides a big deliverable sitting on day 8-14, which is
    # exactly when it is still cheap to start.
    if m["hours14"] > m["hours7"]:
        lines.append("")
        lines.append(f"Próximos 14 dias: {m['hours14']}h em {len(m['next14'])} item(ns).")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# stylesheet
# --------------------------------------------------------------------------

CSS = """
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: light;
  --bg:      #F6F6F4;
  --card:    #FFFFFF;
  --sunken:  #ECECE8;
  --ink:     #1A1A18;
  --muted:   #63635E;
  --faint:   #93938C;
  --line:    #E2E2DC;
  --hair:    #EEEEE9;

  --danger:  #B3261E;
  --danger-soft: #FBE9E7;
  --warn:    #8A5A00;
  --warn-soft:   #FBF0DA;
  --ok:      #1F6D4A;

  --shadow: 0 1px 2px rgba(20,20,18,.05), 0 6px 16px -8px rgba(20,20,18,.10);
  --r: 14px;
  --hour: 27px;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg:      #131315;
    --card:    #1C1C1F;
    --sunken:  #26262A;
    --ink:     #EDEDEA;
    --muted:   #A3A39C;
    --faint:   #74746E;
    --line:    #2E2E33;
    --hair:    #26262A;

    --danger:  #FF9B8F;
    --danger-soft: #3A1E1B;
    --warn:    #F0C070;
    --warn-soft:   #35290F;
    --ok:      #6FD39B;

    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 20px -10px rgba(0,0,0,.55);
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg:      #131315;
  --card:    #1C1C1F;
  --sunken:  #26262A;
  --ink:     #EDEDEA;
  --muted:   #A3A39C;
  --faint:   #74746E;
  --line:    #2E2E33;
  --hair:    #26262A;

  --danger:  #FF9B8F;
  --danger-soft: #3A1E1B;
  --warn:    #F0C070;
  --warn-soft:   #35290F;
  --ok:      #6FD39B;

  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 20px -10px rgba(0,0,0,.55);
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

.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 22px 16px 72px;
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.term {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--faint);
}
h1 {
  font-size: clamp(22px, 5.6vw, 28px);
  font-weight: 650;
  letter-spacing: -0.02em;
  margin: 2px 0 0;
  text-wrap: balance;
}
h2 {
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--faint);
  margin: 0 0 12px;
}
section { display: block; }

/* ---------- hero ---------- */
.hero {
  background: var(--card);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border-top: 4px solid var(--c, var(--line));
}
.hero-label {
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--c, var(--muted));
}
.hero-main { display: flex; gap: 18px; align-items: center; }
.hero-num {
  font-family: var(--mono);
  font-size: clamp(44px, 13vw, 62px);
  font-weight: 600;
  line-height: 0.9;
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
  color: var(--c, var(--ink));
}
.hero-unit {
  display: block;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--faint);
  margin-top: 6px;
}
.hero-title { font-size: 18px; font-weight: 600; line-height: 1.3; text-wrap: pretty; }
.hero-meta { font-size: 14px; color: var(--muted); margin-top: 5px; }

.alert {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  background: var(--danger-soft);
  color: var(--danger);
  border-radius: 10px;
  padding: 11px 13px;
  font-size: 14px;
  font-weight: 500;
}
.alert svg { flex: none; margin-top: 2px; }

/* ---------- workload chart ---------- */
.chart {
  background: var(--card);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 18px 16px 14px;
}
.cap-note { font-size: 12px; color: var(--faint); margin-bottom: 14px; display: flex; align-items: center; gap: 7px; }
.cap-swatch { width: 16px; height: 0; border-top: 2px dashed var(--faint); flex: none; }

.bars { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; align-items: end; height: 132px; position: relative; }
.capline { position: absolute; left: 0; right: 0; border-top: 2px dashed var(--faint); opacity: .55; }
.bar-col { display: flex; flex-direction: column; justify-content: flex-end; height: 100%; gap: 5px; position: relative; }
.bar {
  border-radius: 6px 6px 3px 3px;
  background: linear-gradient(180deg, var(--sunken), var(--sunken));
  min-height: 3px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
}
.bar span { display: block; }
.bar-h { font-family: var(--mono); font-size: 11px; font-weight: 600; text-align: center; color: var(--muted); font-variant-numeric: tabular-nums; }
.bar-col.over .bar-h { color: var(--danger); }
.xaxis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; margin-top: 9px; }
.xlab { font-size: 10px; text-align: center; color: var(--faint); letter-spacing: .02em; line-height: 1.3; }
.xlab.now { color: var(--ink); font-weight: 700; }

/* ---------- filters ---------- */
.chips { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 12px; }
.chip {
  font: inherit;
  font-size: 13px;
  font-weight: 550;
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 7px 14px;
  cursor: pointer;
  min-height: 36px;
}
.chip[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--bg); }
.chip:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }

/* ---------- task list ---------- */
.list { display: flex; flex-direction: column; gap: 8px; }
.item {
  background: var(--card);
  border-radius: 12px;
  box-shadow: var(--shadow);
  overflow: hidden;
  border-left: 4px solid var(--c, var(--line));
}
.item > summary {
  display: flex;
  gap: 13px;
  align-items: center;
  padding: 14px 15px;
  cursor: pointer;
  list-style: none;
  min-height: 56px;
}
.item > summary::-webkit-details-marker { display: none; }
.item > summary:focus-visible { outline: 2px solid var(--ink); outline-offset: -2px; }
.ico { flex: none; color: var(--c, var(--muted)); opacity: .9; }
.it-body { flex: 1; min-width: 0; }
.it-title { font-size: 15px; font-weight: 550; line-height: 1.35; text-wrap: pretty; }
.it-sub { font-size: 12.5px; color: var(--faint); margin-top: 3px; }
.pill {
  flex: none;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .02em;
  padding: 5px 9px;
  border-radius: 999px;
  background: var(--sunken);
  color: var(--muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.sev-late .pill, .sev-now .pill { background: var(--danger-soft); color: var(--danger); }
.sev-soon .pill { background: var(--warn-soft); color: var(--warn); }
.it-note {
  font-size: 14px;
  color: var(--muted);
  padding: 0 15px 15px 15px;
  margin: 0;
  border-top: 1px solid var(--hair);
  padding-top: 12px;
  line-height: 1.55;
}
.item.is-done { opacity: .55; }
.item.is-done .it-title { text-decoration: line-through; }
.list[data-filter="7"]  .item:not([data-in7])  { display: none; }
.list[data-filter="14"] .item:not([data-in14]) { display: none; }
.list[data-filter="late"] .item:not([data-late]) { display: none; }
.empty { font-size: 14px; color: var(--faint); padding: 18px 2px; }

/* ---------- timetable ---------- */
.tt-wrap { background: var(--card); border-radius: var(--r); box-shadow: var(--shadow); padding: 14px 12px 12px; overflow-x: auto; }
.tt { display: grid; grid-template-columns: 32px repeat(5, minmax(52px, 1fr)); gap: 4px; min-width: 300px; }
.tt-head { font-size: 10px; font-weight: 700; letter-spacing: .08em; color: var(--faint); text-align: center; padding-bottom: 6px; }
.tt-head.now { color: var(--ink); }
.tt-hours { position: relative; }
.tt-hours i {
  position: absolute;
  right: 3px;
  transform: translateY(-50%);
  font-family: var(--mono);
  font-size: 9.5px;
  font-style: normal;
  color: var(--faint);
}
.tt-col { position: relative; border-left: 1px solid var(--hair); }
.tt-col.now { background: var(--sunken); border-radius: 5px; }
.blk {
  position: absolute;
  left: 1px; right: 1px;
  border-radius: 5px;
  background: var(--c);
  color: #fff;
  padding: 4px 3px 0;
  font-size: 9.5px;
  font-weight: 650;
  line-height: 1.15;
  overflow: hidden;
}
.blk b { display: block; font-family: var(--mono); font-weight: 600; opacity: .85; font-size: 9px; }
:root[data-theme="dark"] .blk, :root:not([data-theme="light"]) .blk { color: #16161A; }
@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) .blk { color: #fff; } }
.clash-note {
  display: flex; gap: 8px; align-items: flex-start;
  margin-top: 12px; padding: 10px 12px;
  background: var(--warn-soft); color: var(--warn);
  border-radius: 10px; font-size: 13px; font-weight: 500;
}
.clash-note svg { flex: none; margin-top: 2px; }

/* ---------- courses ---------- */
.courses { display: flex; flex-direction: column; gap: 8px; }
.course {
  background: var(--card);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 14px 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-left: 4px solid var(--c, var(--line));
}
.c-top { display: flex; align-items: baseline; gap: 10px; }
.c-name { font-size: 15px; font-weight: 600; flex: 1; line-height: 1.3; }
.c-count { font-family: var(--mono); font-size: 11px; color: var(--faint); white-space: nowrap; }
.c-meta { font-size: 12.5px; color: var(--faint); }
.wbar { display: flex; height: 7px; border-radius: 4px; overflow: hidden; background: var(--sunken); }
.wbar span { display: block; }
.wleg { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11px; color: var(--faint); }
.wleg i { font-style: normal; font-family: var(--mono); }

footer { font-size: 12px; color: var(--faint); line-height: 1.7; border-top: 1px solid var(--line); padding-top: 14px; }

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""

JS = """
document.querySelectorAll('[data-filterbtn]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var list = document.getElementById('tasklist');
    document.querySelectorAll('[data-filterbtn]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b === btn));
    });
    list.setAttribute('data-filter', btn.getAttribute('data-filterbtn'));
  });
});
"""


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def icon(kind: str, size: int = 18) -> str:
    path = TYPE_ICON.get(kind, TYPE_ICON["admin"])
    return (f'<svg class="ico" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true"><path d="{path}"/></svg>')


WARN_SVG = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.9" stroke-linecap="round" aria-hidden="true">'
            '<path d="M12 3l9 16H3z"/><path d="M12 10v4"/><path d="M12 17v.4"/></svg>')


def color_tokens(courses: list[dict]) -> str:
    light = "".join(f"  --c-{c.get('id')}: {c.get('color', '#666')};\n" for c in courses)
    dark = "".join(f"    --c-{c.get('id')}: {c.get('color_dark', c.get('color', '#999'))};\n" for c in courses)
    return (
        f":root {{\n{light}}}\n"
        f"@media (prefers-color-scheme: dark) {{\n  :root:not([data-theme=\"light\"]) {{\n{dark}  }}\n}}\n"
        f":root[data-theme=\"dark\"] {{\n{dark.replace('    ', '  ')}}}\n"
    )


def render_hero(m: dict) -> str:
    t = m["next_up"]
    if not t:
        return ('<section class="hero"><div class="hero-label">Tudo em ordem</div>'
                '<div class="hero-title">Nenhuma entrega em aberto.</div></section>')

    if t["days"] is None:
        num, unit = "—", "sem data"
    elif t["days"] < 0:
        num, unit = str(abs(t["days"])), "dias atrasado"
    elif t["days"] == 0:
        num, unit = "hoje", ""
    else:
        num, unit = str(t["days"]), "dia" if t["days"] == 1 else "dias"

    meta = esc(t["course_name"])
    if t["due"]:
        meta += f" &middot; {br_date(t['due'])}"
        if t["due_time"]:
            meta += f" &middot; {esc(t['due_time'])}"

    alert = ""
    if len(m["late"]) > 1 or (m["late"] and m["late"][0] is not t):
        alert = (f'<div class="alert">{WARN_SVG}<span>{len(m["late"])} item(ns) em atraso — '
                 f'veja a lista abaixo.</span></div>')
    elif m["hours14"] > m["capacity"] * 2:
        alert = (f'<div class="alert">{WARN_SVG}<span>{m["hours14"]}h de trabalho nos próximos 14 dias, '
                 f'contra ~{m["capacity"] * 2}h de capacidade. Algo precisa começar hoje.</span></div>')

    size = "font-size:clamp(30px,8vw,42px)" if num == "hoje" else ""
    return (
        f'<section class="hero" style="--c: var(--c-{esc(t["course_id"])})">'
        f'<div class="hero-label">Próxima entrega</div>'
        f'<div class="hero-main">'
        f'<div><div class="hero-num" style="{size}">{esc(num)}</div>'
        f'<span class="hero-unit">{esc(unit)}</span></div>'
        f'<div class="hero-body"><div class="hero-title">{esc(t["title"])}</div>'
        f'<div class="hero-meta">{meta}</div></div>'
        f'</div>{alert}</section>'
    )


def render_chart(m: dict) -> str:
    cap = m["capacity"]
    peak = max([b["hours"] for b in m["buckets"]] + [cap])
    top = peak * 1.18 or 1

    cols, labs = "", ""
    for b in m["buckets"]:
        pct = 100 * b["hours"] / top
        over = " over" if b["hours"] > cap else ""
        # Stack one segment per course so the bar shows *what* the week is made of.
        segs = ""
        for c in m["courses"]:
            hrs = sum(t["effort"] for t in b["items"] if t["course_id"] == c.get("id"))
            if hrs:
                segs += (f'<span style="height:{100 * hrs / b["hours"]:.3f}%;'
                         f'background:var(--c-{c.get("id")})"></span>')
        cols += (f'<div class="bar-col{over}"><div class="bar-h">{b["hours"] or ""}</div>'
                 f'<div class="bar" style="height:{pct:.3f}%">{segs}</div></div>')
        mark = " now" if b["is_current"] else ""
        labs += (f'<div class="xlab{mark}">{b["start"].day}/{b["start"].month:02d}</div>')

    capline = f'<div class="capline" style="bottom:{100 * cap / top:.3f}%"></div>'
    return (
        f'<section><h2>Carga de trabalho por semana</h2><div class="chart">'
        f'<div class="cap-note"><span class="cap-swatch"></span>'
        f'linha = sua capacidade de {cap}h/semana &middot; cores = disciplinas</div>'
        f'<div class="bars">{capline}{cols}</div><div class="xaxis">{labs}</div>'
        f'</div></section>'
    )


def render_item(t: dict) -> str:
    flags = ""
    if t["days"] is not None and 0 <= t["days"] <= 7:
        flags += " data-in7"
    if t["days"] is not None and 0 <= t["days"] <= 14:
        flags += " data-in14"
    if t["sev"] == "late":
        flags += " data-late"
    done = " is-done" if t["status"] == "done" else ""

    sub = TYPE_PT.get(t["type"], "Item") + " &middot; " + esc(t["course_name"])
    if t["due"]:
        sub += f" &middot; {br_date(t['due'])}"
    if t["effort"]:
        sub += f" &middot; {t['effort']}h"

    note = f'<p class="it-note">{esc(t["notes"])}</p>' if t["notes"] else ""
    tag = "details" if t["notes"] else "div"
    inner = (
        f'{icon(t["type"])}'
        f'<div class="it-body"><div class="it-title">{esc(t["title"])}</div>'
        f'<div class="it-sub">{sub}</div></div>'
        f'<span class="pill">{esc(countdown(t["days"]))}</span>'
    )
    if tag == "details":
        return (f'<details class="item sev-{t["sev"]}{done}"{flags} '
                f'style="--c: var(--c-{esc(t["course_id"])})">'
                f'<summary>{inner}</summary>{note}</details>')
    return (f'<div class="item sev-{t["sev"]}{done}"{flags} '
            f'style="--c: var(--c-{esc(t["course_id"])})">'
            f'<div class="it-summary" style="display:flex;gap:13px;align-items:center;padding:14px 15px">'
            f'{inner}</div></div>')


def render_list(m: dict) -> str:
    chips = [("all", "Tudo"), ("7", "7 dias"), ("14", "14 dias"), ("late", "Atrasado")]
    chip_html = "".join(
        f'<button class="chip" data-filterbtn="{k}" aria-pressed="{str(k == "all").lower()}">{v}</button>'
        for k, v in chips
    )
    rows = "".join(render_item(t) for t in m["open"]) or \
        '<p class="empty">Nada em aberto.</p>'
    return (
        f'<section><h2>Entregas</h2><div class="chips">{chip_html}</div>'
        f'<div class="list" id="tasklist" data-filter="all">{rows}</div></section>'
    )


def render_timetable(m: dict) -> str:
    span = TIMETABLE_END - TIMETABLE_START
    height = span / 60 * 27

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
            top = 100 * (s - TIMETABLE_START) / span
            hgt = 100 * (e - s) / span
            w = 100 / lanes
            blocks += (
                f'<div class="blk" style="--c:var(--c-{course.get("id")});'
                f'top:{top:.3f}%;height:{hgt:.3f}%;left:{lane * w:.3f}%;width:{w:.3f}%">'
                f'<b>{esc(slot.get("start"))}</b>{esc(course.get("name"))}</div>'
            )
        cols += (f'<div class="tt-col{" now" if k == todays_key else ""}" '
                 f'style="height:{height:.0f}px">{blocks}</div>')

    note = ""
    if m["clashes"]:
        pairs = "; ".join(f"{a} × {b}" for v in m["clashes"].values() for a, b in v)
        note = f'<div class="clash-note">{WARN_SVG}<span>Choque de horário: {esc(pairs)}</span></div>'

    return (f'<section><h2>Semana de aulas</h2><div class="tt-wrap">'
            f'<div class="tt">{heads}{cols}</div>{note}</div></section>')


def render_courses(m: dict) -> str:
    cards = ""
    for c in m["courses"]:
        cid = c.get("id")
        mine = [t for t in m["tasks"] if t["course_id"] == cid]
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
                op = 1 - (i * 0.19)
                segs.append(f'<span style="width:{100 * w / total:.3f}%;'
                            f'background:var(--c-{cid});opacity:{op:.2f}"></span>')
                legs.append(f'<span>{esc(g.get("item"))} <i>{w}%</i></span>')
            bar = f'<div class="wbar">{"".join(segs)}</div>'
            leg = f'<div class="wleg">{"".join(legs)}</div>'

        cards += (
            f'<div class="course" style="--c: var(--c-{cid})">'
            f'<div class="c-top"><div class="c-name">{esc(c.get("name"))}</div>'
            f'<div class="c-count">{open_n} aberto{"s" if open_n != 1 else ""}</div></div>'
            f'<div class="c-meta">{" &middot; ".join(meta)}</div>{bar}{leg}</div>'
        )
    return f'<section><h2>Disciplinas</h2><div class="courses">{cards}</div></section>'


def render_html(m: dict) -> str:
    today = m["today"]
    heading = f"{FULLDAY_PT[today.weekday()]}, {today.day} de {FULLMONTH_PT[today.month - 1]}"

    return f"""<title>Painel do Mestrado</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#F6F6F4">
<style>{CSS}{color_tokens(m['courses'])}</style>
<div class="page">
  <header>
    <div class="term">{esc(m['term'])} &middot; UFSC &middot; 5 disciplinas</div>
    <h1>{heading}</h1>
  </header>

  {render_hero(m)}
  {render_chart(m)}
  {render_list(m)}
  {render_timetable(m)}
  {render_courses(m)}

  <footer>
    Atualizado em {dt.datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC a partir de
    study/courses.yml e study/tasks.yml.<br>
    Contagens relativas a {today.strftime('%d/%m/%Y')} em {esc(m['tz'])}.
  </footer>
</div>
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
