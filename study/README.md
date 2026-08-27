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

## Confirmed vs estimated dates

Only Ciência de Dados publishes real dates — its cronograma lists them
explicitly, and those are marked `CONFIRMED` in `tasks.yml`.

The three PPGEAS courses (ML, IA, SMA) number their weeks instead of dating
them, so their milestones are `ESTIMATED`: derived from the week number,
anchored to the 10 Aug term start, and every plan warns the cronograma "may be
modified". Treat them as placeholders that keep the work visible until a real
date replaces them. When a professor names a date, tell me and I will promote
it to confirmed.

Estatística para Análise de Dados has no teaching plan at all. One of the five
disciplines is invisible here, and that is the biggest gap in this tracker.

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

## Saving

The page writes changes back into the artifact itself, so ticking something off
survives a cleared browser or a different device. Every change lands in device
storage immediately and a debounced publish (about four seconds after the last
one) writes the state into the published page as a `<script id="state">` block.
If the capability is missing or the viewer is read-only it degrades to device
storage alone and says so.

**Rebuilding from this side needs one extra step.** A rebuild here would ship a
fresh page whose embedded state is empty, wiping what was ticked off. So before
running the build, pull the live state down and drop it in `study/state.json`:
read the published artifact, copy the contents of its `<script id="state">`
block into that file, then rebuild. The build bakes it in as the starting state.

## The morning brief

The brief is rendered at the top of the page itself, from the same data, so it
is current whenever it is opened rather than being a snapshot of 07:12.

The scheduled job that used to send it every morning is disabled. It also used
to republish the page daily, which is what wiped the reader's ticked-off work:
the page now derives the current date from the device, so it never needs a
scheduled refresh.
