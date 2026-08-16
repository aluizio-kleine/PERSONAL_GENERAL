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
DAY_LABEL = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}
DAY_SHORT = {k: k.upper() for k in DAY_KEYS}

TYPE_LABEL = {
    "assignment": "Assignment", "exam": "Exam", "reading": "Reading",
    "paper": "Paper", "presentation": "Presentation", "admin": "Admin",
}


# --------------------------------------------------------------------------
# data loading
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


def as_date(value) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# derived model
# --------------------------------------------------------------------------

def severity(days: int | None, status: str) -> str:
    if status == "done":
        return "done"
    if days is None:
        return "calm"
    if days < 0:
        return "late"
    if days == 0:
        return "now"
    if days <= 2:
        return "soon"
    if days <= 7:
        return "week"
    return "calm"


def countdown_label(days: int | None) -> str:
    if days is None:
        return "no date"
    if days < 0:
        return f"{abs(days)}d late"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"{days}d"


def build_model(courses_doc: dict, tasks_doc: dict) -> dict:
    tz = courses_doc.get("timezone") or "America/Sao_Paulo"
    today = today_in(tz)
    courses = courses_doc.get("courses") or []
    by_id = {c.get("id"): c for c in courses}

    tasks = []
    for raw in (tasks_doc.get("tasks") or []):
        due = as_date(raw.get("due"))
        days = (due - today).days if due else None
        status = (raw.get("status") or "todo").lower()
        course = by_id.get(raw.get("course"))
        tasks.append({
            "id": raw.get("id"),
            "title": raw.get("title") or "(untitled)",
            "type": (raw.get("type") or "assignment").lower(),
            "course_name": (course or {}).get("name", "Unassigned"),
            "course_id": raw.get("course"),
            "due": due,
            "due_time": raw.get("due_time") or "",
            "days": days,
            "effort": raw.get("effort") or 0,
            "status": status,
            "notes": raw.get("notes") or "",
            "sev": severity(days, status),
        })

    # Open work sorts by urgency; undated work sinks to the bottom.
    open_tasks = [t for t in tasks if t["status"] != "done"]
    open_tasks.sort(key=lambda t: (t["days"] is None, t["days"] if t["days"] is not None else 0))
    done_tasks = [t for t in tasks if t["status"] == "done"]

    todays_key = DAY_KEYS[today.weekday()]
    todays_classes = []
    for c in courses:
        for slot in (c.get("schedule") or []):
            if (slot.get("day") or "").lower() == todays_key:
                todays_classes.append({"course": c, "slot": slot})
    todays_classes.sort(key=lambda x: x["slot"].get("start") or "")

    week = {k: [] for k in DAY_KEYS}
    for c in courses:
        for slot in (c.get("schedule") or []):
            key = (slot.get("day") or "").lower()
            if key in week:
                week[key].append({"course": c, "slot": slot})
    for key in week:
        week[key].sort(key=lambda x: x["slot"].get("start") or "")

    horizon = [t for t in open_tasks if t["days"] is not None and 0 <= t["days"] <= 7]
    return {
        "today": today,
        "tz": tz,
        "term": courses_doc.get("term") or "",
        "courses": courses,
        "tasks": tasks,
        "open": open_tasks,
        "done": done_tasks,
        "todays_classes": todays_classes,
        "todays_tasks": [t for t in open_tasks if t["days"] == 0],
        "week": week,
        "late": [t for t in open_tasks if t["days"] is not None and t["days"] < 0],
        "next7": horizon,
        "hours7": sum(t["effort"] for t in horizon),
    }


# --------------------------------------------------------------------------
# plain-text brief (used by the scheduled morning push)
# --------------------------------------------------------------------------

def brief(m: dict) -> str:
    lines = [f"{m['today'].strftime('%a %d %b %Y')}"]

    if m["late"]:
        lines.append("")
        lines.append(f"OVERDUE ({len(m['late'])}):")
        for t in m["late"]:
            lines.append(f"  - {t['title']} [{t['course_name']}] {countdown_label(t['days'])}")

    if m["todays_classes"]:
        lines.append("")
        lines.append("Classes today:")
        for item in m["todays_classes"]:
            slot = item["slot"]
            where = slot.get("where") or ""
            times = f"{slot.get('start','')}-{slot.get('end','')}".strip("-")
            lines.append(f"  - {times} {item['course']['name']}" + (f" ({where})" if where else ""))
    else:
        lines.append("")
        lines.append("No classes today.")

    due_soon = [t for t in m["open"] if t["days"] is not None and 0 <= t["days"] <= 7]
    if due_soon:
        lines.append("")
        lines.append(f"Due within 7 days ({m['hours7']}h of work):")
        for t in due_soon:
            lines.append(f"  - {countdown_label(t['days']):>10}  {t['title']} [{t['course_name']}]")
    else:
        lines.append("")
        lines.append("Nothing due in the next 7 days.")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

CSS = """
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: light;
  --bg:      #EFF1F5;
  --surface: #FFFFFF;
  --sunken:  #E4E7EE;
  --ink:     #14161D;
  --muted:   #5B6274;
  --faint:   #878FA3;
  --line:    #D8DCE5;
  --accent:  #3F51C4;

  --late-fg: #A6301C;  --late-bg: #F7DED8;
  --now-fg:  #A6301C;  --now-bg:  #F7DED8;
  --soon-fg: #8A5606;  --soon-bg: #F8E7C9;
  --week-fg: #2C4499;  --week-bg: #DFE4F8;
  --calm-fg: #5B6274;  --calm-bg: #E4E7EE;
  --done-fg: #2C6A4F;  --done-bg: #D9EBE1;

  --mono: ui-monospace, "SF Mono", "JetBrains Mono", "Roboto Mono", Menlo, Consolas, monospace;
  --sans: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg:      #0F1118;
    --surface: #171A23;
    --sunken:  #1E222D;
    --ink:     #E7EAF2;
    --muted:   #969DB1;
    --faint:   #6C7386;
    --line:    #262B38;
    --accent:  #8494F2;

    --late-fg: #F0A08D;  --late-bg: #3B1F1A;
    --now-fg:  #F0A08D;  --now-bg:  #3B1F1A;
    --soon-fg: #E5B871;  --soon-bg: #382A14;
    --week-fg: #A8B4F7;  --week-bg: #202741;
    --calm-fg: #969DB1;  --calm-bg: #1E222D;
    --done-fg: #85C7A6;  --done-bg: #172B22;
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg:      #0F1118;
  --surface: #171A23;
  --sunken:  #1E222D;
  --ink:     #E7EAF2;
  --muted:   #969DB1;
  --faint:   #6C7386;
  --line:    #262B38;
  --accent:  #8494F2;

  --late-fg: #F0A08D;  --late-bg: #3B1F1A;
  --now-fg:  #F0A08D;  --now-bg:  #3B1F1A;
  --soon-fg: #E5B871;  --soon-bg: #382A14;
  --week-fg: #A8B4F7;  --week-bg: #202741;
  --calm-fg: #969DB1;  --calm-bg: #1E222D;
  --done-fg: #85C7A6;  --done-bg: #172B22;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

.wrap {
  max-width: 980px;
  margin: 0 auto;
  padding: 20px 16px 64px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.eyebrow {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--faint);
  margin: 0;
}

h1 {
  font-family: var(--mono);
  font-size: clamp(24px, 6vw, 34px);
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: 4px 0 0;
  text-wrap: balance;
}

h2 {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}

section { display: block; }

/* ---- status strip ---- */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
  margin-top: 16px;
}
.stat {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat .n {
  font-family: var(--mono);
  font-size: 26px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.stat .k {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--faint);
}
.stat.alarm { border-color: var(--late-fg); }
.stat.alarm .n { color: var(--late-fg); }

/* ---- board rows ---- */
.board { display: flex; flex-direction: column; gap: 6px; }

.row {
  position: relative;
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 12px;
  align-items: start;
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--stripe, var(--line));
  border-radius: 3px;
  padding: 11px 13px;
}
.row .cd {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--chip-fg, var(--muted));
  background: var(--chip-bg, var(--sunken));
  border-radius: 2px;
  padding: 4px 6px;
  text-align: center;
  white-space: nowrap;
}
.row .title { font-weight: 500; text-wrap: pretty; }
.row .meta {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.03em;
  color: var(--faint);
  margin-top: 3px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}
.row .note {
  font-size: 13px;
  color: var(--muted);
  margin-top: 5px;
}
.row.is-done .title { text-decoration: line-through; color: var(--faint); }

.sev-late { --stripe: var(--late-fg); --chip-fg: var(--late-fg); --chip-bg: var(--late-bg); }
.sev-now  { --stripe: var(--now-fg);  --chip-fg: var(--now-fg);  --chip-bg: var(--now-bg); }
.sev-soon { --stripe: var(--soon-fg); --chip-fg: var(--soon-fg); --chip-bg: var(--soon-bg); }
.sev-week { --stripe: var(--week-fg); --chip-fg: var(--week-fg); --chip-bg: var(--week-bg); }
.sev-calm { --stripe: var(--line);    --chip-fg: var(--calm-fg); --chip-bg: var(--calm-bg); }
.sev-done { --stripe: var(--done-fg); --chip-fg: var(--done-fg); --chip-bg: var(--done-bg); }

/* ---- today ---- */
.today-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.classline {
  display: flex;
  gap: 12px;
  align-items: baseline;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--line);
}
.classline:last-child { border-bottom: 0; padding-bottom: 0; }
.classline .t {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
  white-space: nowrap;
}
.classline .w {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--faint);
}
.empty {
  font-size: 14px;
  color: var(--muted);
  font-style: italic;
}

/* ---- week grid ---- */
.week {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}
@media (min-width: 760px) {
  .week { grid-template-columns: repeat(7, 1fr); }
}
.day {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 9px 10px;
  min-height: 62px;
}
.day.is-today { border-color: var(--accent); background: var(--sunken); }
.day .dh {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--faint);
  margin-bottom: 6px;
}
.day.is-today .dh { color: var(--accent); font-weight: 600; }
.day .ev { font-size: 12px; line-height: 1.35; margin-bottom: 7px; }
.day .ev:last-child { margin-bottom: 0; }
.day .ev b { display: block; font-family: var(--mono); font-size: 11px; font-weight: 600; color: var(--muted); }

/* ---- courses ---- */
.courses {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 8px;
}
.course {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 13px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.course .cn { font-weight: 600; line-height: 1.3; }
.course .cm {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--faint);
  display: flex;
  flex-wrap: wrap;
  gap: 3px 10px;
}
.weights { display: flex; height: 6px; border-radius: 2px; overflow: hidden; background: var(--sunken); }
.weights span { display: block; }
.wlegend {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--faint);
  display: flex;
  flex-wrap: wrap;
  gap: 3px 10px;
}

footer {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--faint);
  border-top: 1px solid var(--line);
  padding-top: 12px;
  line-height: 1.6;
}
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def render_row(t: dict) -> str:
    done = " is-done" if t["status"] == "done" else ""
    bits = [TYPE_LABEL.get(t["type"], t["type"].title()), esc(t["course_name"])]
    if t["due"]:
        stamp = t["due"].strftime("%a %d %b")
        if t["due_time"]:
            stamp += f" {t['due_time']}"
        bits.append(stamp)
    if t["effort"]:
        bits.append(f"{t['effort']}h")
    if t["status"] == "doing":
        bits.append("in progress")
    if t["status"] == "blocked":
        bits.append("blocked")

    note = f'<div class="note">{esc(t["notes"])}</div>' if t["notes"] else ""
    return (
        f'<div class="row sev-{t["sev"]}{done}">'
        f'<div class="cd">{esc(countdown_label(t["days"]))}</div>'
        f'<div><div class="title">{esc(t["title"])}</div>'
        f'<div class="meta">{"".join(f"<span>{b}</span>" for b in bits)}</div>'
        f"{note}</div></div>"
    )


WEIGHT_COLORS = ["var(--accent)", "var(--week-fg)", "var(--soon-fg)", "var(--done-fg)", "var(--calm-fg)"]


def render_course(c: dict, model: dict) -> str:
    cid = c.get("id")
    mine = [t for t in model["tasks"] if t["course_id"] == cid]
    open_n = len([t for t in mine if t["status"] != "done"])
    done_n = len([t for t in mine if t["status"] == "done"])

    meta = []
    if c.get("code"):
        meta.append(esc(c["code"]))
    if c.get("professor"):
        meta.append(esc(c["professor"]))
    slots = c.get("schedule") or []
    for s in slots:
        key = (s.get("day") or "").lower()
        meta.append(f"{DAY_SHORT.get(key, key.upper())} {esc(s.get('start',''))}")
    meta.append(f"{open_n} open / {done_n} done")

    grading = c.get("grading") or []
    total = sum(g.get("weight") or 0 for g in grading)
    bar = legend = ""
    if total > 0:
        segs, legs = [], []
        for i, g in enumerate(grading):
            w = g.get("weight") or 0
            if w <= 0:
                continue
            color = WEIGHT_COLORS[i % len(WEIGHT_COLORS)]
            pct = 100 * w / total
            segs.append(f'<span style="width:{pct:.4f}%;background:{color}"></span>')
            legs.append(f'<span>{esc(g.get("item",""))} {w}%</span>')
        bar = f'<div class="weights">{"".join(segs)}</div>'
        legend = f'<div class="wlegend">{"".join(legs)}</div>'

    return (
        f'<div class="course"><div class="cn">{esc(c.get("name","(unnamed)"))}</div>'
        f'<div class="cm">{"".join(f"<span>{b}</span>" for b in meta)}</div>'
        f"{bar}{legend}</div>"
    )


def render_html(m: dict) -> str:
    today = m["today"]
    late_n = len(m["late"])

    stats = [
        ("alarm" if late_n else "", late_n, "overdue"),
        ("", len(m["todays_tasks"]), "due today"),
        ("", len(m["next7"]), "due in 7 days"),
        ("", f"{m['hours7']}h", "work queued"),
        ("", len(m["open"]), "open total"),
    ]
    stats_html = "".join(
        f'<div class="stat {cls}"><span class="n">{esc(n)}</span><span class="k">{esc(k)}</span></div>'
        for cls, n, k in stats
    )

    if m["todays_classes"]:
        classes_html = "".join(
            '<div class="classline">'
            f'<span class="t">{esc(i["slot"].get("start",""))}&ndash;{esc(i["slot"].get("end",""))}</span>'
            f'<span><b>{esc(i["course"].get("name",""))}</b>'
            + (f'<span class="w"> &nbsp;{esc(i["slot"].get("where"))}</span>' if i["slot"].get("where") else "")
            + "</span></div>"
            for i in m["todays_classes"]
        )
    else:
        classes_html = '<div class="empty">No classes scheduled today.</div>'

    # m["open"] is already sorted by days-remaining, so overdue items lead.
    board_html = "".join(render_row(t) for t in m["open"]) or \
        '<div class="empty">Nothing open. Either you are on top of everything, or the tracker is out of date.</div>'

    week_html = ""
    todays_key = DAY_KEYS[today.weekday()]
    for key in DAY_KEYS:
        cls = " is-today" if key == todays_key else ""
        evs = "".join(
            f'<div class="ev"><b>{esc(i["slot"].get("start",""))}</b>{esc(i["course"].get("name",""))}</div>'
            for i in m["week"][key]
        )
        week_html += f'<div class="day{cls}"><div class="dh">{DAY_SHORT[key]}</div>{evs}</div>'

    courses_html = "".join(render_course(c, m) for c in m["courses"]) or \
        '<div class="empty">No courses registered yet.</div>'

    done_note = ""
    if m["done"]:
        done_note = f" &middot; {len(m['done'])} task(s) completed and archived"

    return f"""<title>Master's Term Board</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
<div class="wrap">
  <header>
    <p class="eyebrow">Term {esc(m['term'])} &middot; {esc(m['tz'])}</p>
    <h1>{today.strftime('%A, %d %B %Y')}</h1>
    <div class="stats">{stats_html}</div>
  </header>

  <section>
    <h2>Today</h2>
    <div class="today-card">
      {classes_html}
      {"".join(render_row(t) for t in m["todays_tasks"])}
    </div>
  </section>

  <section>
    <h2>Deadline board</h2>
    <div class="board">{board_html}</div>
  </section>

  <section>
    <h2>Week</h2>
    <div class="week">{week_html}</div>
  </section>

  <section>
    <h2>Disciplines</h2>
    <div class="courses">{courses_html}</div>
  </section>

  <footer>
    Generated {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC from study/courses.yml and study/tasks.yml{done_note}.<br>
    Countdowns are relative to {today.isoformat()} in {esc(m['tz'])}.
  </footer>
</div>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", action="store_true", help="print the plain-text daily brief instead of building HTML")
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
