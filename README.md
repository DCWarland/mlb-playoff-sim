# Blue Jays playoff simulator

A single-file web app that plays out the rest of the 2026 MLB season thousands of
times and reports how often the Blue Jays reach the postseason. Real schedule,
real standings, real tiebreaker rules.

## Use it

Double-click `index.html`, or from a terminal:

```
open index.html
```

No server, no install, no internet needed once the data is baked in.

## Automatic updates on GitHub

`.github/workflows/refresh.yml` keeps the page current by itself. It runs:

- **daily at 11:30 UTC** (7:30am Eastern — after the last west-coast game is final)
- **on every push** to `main`
- **on demand**, via the Run workflow button in the Actions tab

Each run pulls the latest standings and schedule, rewrites the data block in
`index.html`, commits it if anything changed, and publishes to GitHub Pages.

**One-time setup after you create the repo:**

1. Settings → Pages → Source: **GitHub Actions**
2. Settings → Actions → General → Workflow permissions: **Read and write**

The auto-commit message ends with `[skip ci]` so committing doesn't re-trigger the
push event and loop forever.

## Refresh the data by hand

The standings and remaining schedule are stored inside `index.html`. To pull
today's numbers from MLB's public Stats API and write them back into the page:

```
python3 refresh_data.py
```

It only touches the block between the `<!--DATA-START-->` and `<!--DATA-END-->`
markers, so anything you change elsewhere in the page survives. It also checks
that every American League club's games played plus games remaining adds to 162,
and warns you if MLB's feed doesn't reconcile.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app — markup, styles, simulation, charts, and the baked-in data |
| `refresh_data.py` | Downloads fresh data and injects it into `index.html` |
| `history.json` | One row per day of the season, written by the refresh job |

## Layout

Controls live in the left rail under three tabs; views are tabbed across the top.

**Rail — Jays / League / Model**

- **Jays** — a win rate per opponent, or an exact record in the other mode
- **League** — every club's strength. Type a win total into the figure beside the
  slider and it solves for the strength that produces it.
- **Model** — home-field edge, regression to .500, weight on run difference

**Views — Forecast / Matchups / Standings / Magic / Season / Tonight / Schedule / Method**

**Any club.** Pick one from the masthead and the whole page follows it, either league.

**Forecast** ends with an October funnel: the chance of surviving each round through
to the World Series, simulated game by game with real series formats.

**Season** replays the whole year. Every finished game is archived with its date and
winner, so any past day's standings rebuild exactly and the odds can be re-simulated
from what was known at the time. Nothing had to be collected going forward.

**Tonight** ranks the next day's games by how much each one moves your odds, and tells
you who to root for. Both branches of a game use identical random numbers, so the
difference between them is the effect of that result rather than sampling noise.

**Link** in the masthead copies a URL carrying your entire scenario — club, sliders,
every override — so it opens for someone else exactly as you left it.

**Magic** is the one tab the controls don't touch. A magic number is arithmetic on
games already played — how many combined events (your wins plus their losses) must
land before a result is guaranteed. `M(a,b) = (W_b + games_b_left) - W_a + 1`, which
read from the other side is *b*'s elimination number against *a*. So one 15×15 grid
answers both questions. It moves once a day on real results, and shows how each
number changed overnight.

**Matchups** is the full-control sheet: all 116 pairs of clubs with games left.
`Model` simulates from strength, `Rate` fixes a win percentage, `Pin` fixes an exact
result. Adjusting either side moves both clubs, because a game one wins is a game the
other loses. The rail and this sheet are two views of one state, so they cannot disagree.

Projected records are exact arithmetic and update instantly. Playoff odds need a
simulation, so they show a quick estimate while you drag and settle a moment after you stop.

## How the model works

Explained in plain language in the **How this works** section at the bottom of
the page itself.
