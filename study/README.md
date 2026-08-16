# Study tracker

A memory for the five disciplines. No server, no bot, no API keys — the data
lives in this repo as plain text, and a scheduled Claude session reads it each
morning and pushes you a brief.

## The three pieces

| Piece | What it is |
|---|---|
| `courses.yml` | The five disciplines: schedule, professor, how the grade is composed. |
| `tasks.yml` | Every deliverable, exam, reading and errand, with a due date and an effort estimate. |
| `build_dashboard.py` | Turns both files into `dashboard.html` — the page you keep bookmarked on your phone. |

## Day to day

**You never edit YAML by hand unless you want to.** Open a session here and
talk normally:

- "I have a paper for Statistical Inference due the 3rd, probably 10 hours of work"
- "Machine Learning moved to Wednesdays at 19:00"
- "Finished problem set 3"
- "Here's the syllabus for the fifth discipline" *(paste or upload it)*

I update the files, rebuild the dashboard, commit, and republish the page at
the same URL.

## Running it yourself

```bash
python3 study/build_dashboard.py            # rebuild dashboard.html
python3 study/build_dashboard.py --brief    # plain-text summary, no HTML
```

Requires `pyyaml`.

## How urgency is computed

Every open task gets a countdown relative to today in the timezone set in
`courses.yml`, and a severity that drives the colour of its stripe and chip:

| Severity | When |
|---|---|
| `late` | past its due date |
| `now` | due today |
| `soon` | due within 2 days |
| `week` | due within 7 days |
| `calm` | further out, or no date set |

`effort` hours for everything due in the next 7 days are summed into the
"work queued" figure. That number is the early-warning signal: when it climbs
past what a week can actually absorb, the crunch is visible while there is
still time to move something.

## The morning brief

A scheduled task wakes a fresh Claude session each morning, pulls this repo,
runs `--brief`, and pushes you the result. It stays silent on days when there
is nothing overdue and nothing due within the week, so it does not become
noise you learn to ignore.

To change the time, the timezone, or switch it off, just say so.
