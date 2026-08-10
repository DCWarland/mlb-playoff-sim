#!/usr/bin/env python3
"""
Refresh the simulator with today's real MLB data.

    python3 refresh_data.py

It downloads the current standings and the full season schedule from MLB's
public Stats API, squeezes them into a small JSON blob, and writes that blob
into index.html between the DATA-START / DATA-END markers. Nothing else in
index.html is touched, so you can edit the page freely and re-run this any time.

No API key, no dependencies beyond the Python standard library.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

# Defaults to the current year so this keeps working next season untouched.
# Override with MLB_SEASON=2025 to look at an older year.
SEASON = int(os.environ.get("MLB_SEASON") or datetime.date.today().year)
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "index.html")
START, END = "<!--DATA-START-->", "<!--DATA-END-->"

API = "https://statsapi.mlb.com/api/v1"
DIV_ORDER = {201: 0, 202: 1, 200: 2, 204: 0, 205: 1, 203: 2}   # East, Central, West
DIV_NAME = {201: "AL East", 202: "AL Central", 200: "AL West",
            204: "NL East", 205: "NL Central", 203: "NL West"}


class SeasonNotPublished(Exception):
    """The API has no such season yet — normal in the winter, not an error."""


def get(url, tries=4):
    """Fetch JSON. Retries only what is worth retrying: timeouts, network errors,
    rate limits and 5xx. A 404 or other 4xx is a permanent answer, so retrying it
    just wastes a minute before failing anyway."""
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mlb-playoff-sim"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise SeasonNotPublished(url) from None
            if e.code < 500 and e.code != 429:
                sys.exit(f"ERROR: {url} returned HTTP {e.code} — {e.reason}")
            err = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            err = e
        if attempt == tries:
            sys.exit(f"ERROR: giving up on {url} after {tries} tries — {err}")
        wait = 3 * attempt
        print(f"  attempt {attempt} failed ({err}); retrying in {wait}s")
        time.sleep(wait)


LOGO_DIR = "logos"
LOGO_SRC = "https://www.mlbstatic.com/team-logos/team-cap-on-{tone}/{tid}.svg"


def fetch_logos(order):
    """Pull each club's cap logo once and keep it in the repo, so the page loads
    them from its own origin instead of hotlinking MLB's servers on every visit.

    Two tones: the light one is drawn for a pale background, the dark one leans on
    white for a black one. Already-downloaded files are left alone, so the daily
    job does not hammer their CDN for artwork that never changes."""
    os.makedirs(os.path.join(HERE, LOGO_DIR), exist_ok=True)
    got = skipped = failed = 0
    for m in order:
        for tone in ("light", "dark"):
            path = os.path.join(HERE, LOGO_DIR, f"{tone}-{m['id']}.svg")
            if os.path.exists(path) and os.path.getsize(path) > 200:
                skipped += 1
                continue
            url = LOGO_SRC.format(tone=tone, tid=m["id"])
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "mlb-playoff-sim"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                if len(data) < 200 or b"<svg" not in data[:200]:
                    raise ValueError("not an svg")
                open(path, "wb").write(data)
                got += 1
            except Exception as e:                      # a missing logo is cosmetic
                failed += 1
                print(f"  logo {m['abbr']} {tone}: {e} (the page falls back to a colour mark)")
    print(f"Logos: {got} downloaded, {skipped} already present"
          + (f", {failed} unavailable" if failed else "") + ".")


def main():
    print(f"Downloading the {SEASON} season from the MLB Stats API…")
    try:
        teams_raw = get(f"{API}/teams?sportId=1&season={SEASON}"
                        "&fields=teams,id,name,teamName,abbreviation,division,league,shortName")["teams"]
        standings = get(f"{API}/standings?leagueId=103,104&season={SEASON}"
                        "&standingsTypes=regularSeason")["records"]
        schedule = get(f"{API}/schedule?sportId=1&season={SEASON}&gameType=R"
                       f"&startDate={SEASON}-03-01&endDate={SEASON}-11-01"
                       "&fields=dates,date,games,gamePk,status,codedGameState,"
                       "teams,home,away,team,id,score,isWinner")["dates"]
    except SeasonNotPublished:
        print(f"MLB has not published a {SEASON} season — nothing to refresh. "
              "Leaving index.html alone.")
        return

    meta = {}
    for t in teams_raw:
        meta[t["id"]] = {
            "id": t["id"], "abbr": t["abbreviation"], "name": t["teamName"],
            "full": t["name"], "city": t["shortName"],
            "lg": 0 if t["league"]["id"] == 103 else 1,
            "div": DIV_ORDER[t["division"]["id"]],
            "divName": DIV_NAME[t["division"]["id"]],
        }

    # Official standings are the authority on today's win-loss record.
    for rec in standings:
        for tr in rec["teamRecords"]:
            m = meta[tr["team"]["id"]]
            m["w"] = tr["leagueRecord"]["wins"]
            m["l"] = tr["leagueRecord"]["losses"]
            m["gb"] = tr["gamesBack"]
            m["wcgb"] = tr["wildCardGamesBack"]
            m["streak"] = tr.get("streak", {}).get("streakCode", "-")
            m["l10"] = "-"
            for sr in tr["records"]["splitRecords"]:
                if sr["type"] == "lastTen":
                    m["l10"] = f"{sr['wins']}-{sr['losses']}"

    # Index order: AL 0-14 (grouped by division), NL 15-29. The simulation
    # relies on "index < 15 means American League".
    al = sorted((m for m in meta.values() if m["lg"] == 0), key=lambda m: (m["div"], -m["w"]))
    nl = sorted((m for m in meta.values() if m["lg"] == 1), key=lambda m: (m["div"], -m["w"]))
    order = al + nl
    idx = {}
    for i, m in enumerate(order):
        m["i"] = i
        idx[m["id"]] = i
    NAL = len(al)

    rs, ra = defaultdict(int), defaultdict(int)
    NT = len(order)
    h2h = [[0] * NT for _ in range(NT)]
    divrec = [[0, 0] for _ in range(NT)]
    learec = [[0, 0] for _ in range(NT)]
    remaining, played, dates, date_idx = [], [], [], {}
    last_final = ""

    for day in schedule:
        for g in day["games"]:
            state = g["status"]["codedGameState"]
            h, a = g["teams"]["home"], g["teams"]["away"]
            hi, ai = idx[h["team"]["id"]], idx[a["team"]["id"]]

            if state == "F":
                if h.get("score") is None or a.get("score") is None:
                    continue
                last_final = max(last_final, day["date"])
                if day["date"] not in date_idx:
                    date_idx[day["date"]] = len(dates)
                    dates.append(day["date"])
                # 1 = the home club won. Enough to replay the season day by day.
                played.append([date_idx[day["date"]], ai, hi, 1 if h.get("isWinner") else 0])
                rs[hi] += h["score"]; ra[hi] += a["score"]
                rs[ai] += a["score"]; ra[ai] += h["score"]
                wi, li = (hi, ai) if h.get("isWinner") else (ai, hi)
                # Tiebreakers only count games inside a club's own league, so
                # interleague results move the record but nothing else.
                if order[wi]["lg"] == order[li]["lg"]:
                    h2h[wi][li] += 1
                    learec[wi][0] += 1
                    learec[li][1] += 1
                    if order[wi]["div"] == order[li]["div"]:
                        divrec[wi][0] += 1
                        divrec[li][1] += 1
            elif state == "S":
                # Every remaining game in both leagues. Postponed games ("D") are
                # skipped: MLB already lists the makeup as its own scheduled game.
                if day["date"] not in date_idx:
                    date_idx[day["date"]] = len(dates)
                    dates.append(day["date"])
                remaining.append([date_idx[day["date"]], ai, hi])

    for m in order:
        i = m["i"]
        e = 1.83                       # Pythagorean exponent for baseball
        m["rs"], m["ra"] = rs[i], ra[i]
        m["pyth"] = round(rs[i] ** e / (rs[i] ** e + ra[i] ** e), 5) if rs[i] else 0.5
        m["pct"] = round(m["w"] / (m["w"] + m["l"]), 5)
        m["gp"] = m["w"] + m["l"]
        m["rem"] = 162 - m["gp"]

    # Sanity check: for every AL club, games played + games left must be 162.
    left = defaultdict(int)
    for _, a, h in remaining:
        left[a] += 1
        left[h] += 1
    bad = [(m["abbr"], left[m["i"]], m["rem"]) for m in order if left[m["i"]] != m["rem"]]
    if bad:
        print("WARNING: scheduled game counts do not reconcile with games played:", bad)
        print("The simulation still runs, but a team's season may not total 162 games.")

    # Carry forward the previous day's records so the page can show how each
    # magic number moved overnight. Only rolls over when the feed has actually
    # advanced a day, so re-running this twice on one afternoon keeps yesterday
    # as yesterday instead of wiping it.
    prev = None
    try:
        old_html = open(PAGE, encoding="utf-8").read()
        tag = '<script id="mlb-data" type="application/json">'
        a = old_html.find(tag)
        b = old_html.find("</script>", a)
        if a >= 0 and b >= 0:
            old = json.loads(old_html[a + len(tag):b])
            old_date = old.get("lastGameDate")
            if old_date and old_date < last_final and old.get("teams"):
                prev = {"date": old_date,
                        "w": {t["abbr"]: t["w"] for t in old["teams"]},
                        "l": {t["abbr"]: t["l"] for t in old["teams"]}}
            elif old_date == last_final:
                prev = old.get("prev")          # same day: keep what we had
    except (OSError, ValueError, KeyError):
        prev = None

    # ---- the season archive -------------------------------------------------
    # One row per day: the date and every club's win-loss record. Only raw facts
    # are stored, never derived odds, so the model can change later and the whole
    # history stays consistent because it gets recomputed from these.
    # This is the one thing that cannot be backfilled — a day not recorded is
    # gone — so it is written even when nothing else changed.
    hist_path = os.path.join(HERE, "history.json")
    try:
        hist = json.load(open(hist_path, encoding="utf-8"))
        if not isinstance(hist, dict) or "days" not in hist:
            hist = {"season": SEASON, "days": []}
    except (OSError, ValueError):
        hist = {"season": SEASON, "days": []}
    if hist.get("season") != SEASON:
        hist = {"season": SEASON, "days": []}

    abbrs = [m["abbr"] for m in order]
    today_row = {"d": last_final, "w": [m["w"] for m in order], "l": [m["l"] for m in order]}
    days = [d for d in hist["days"] if d.get("d") != last_final]
    days.append(today_row)
    days.sort(key=lambda d: d["d"])
    hist = {"season": SEASON, "abbrs": abbrs, "days": days}
    json.dump(hist, open(hist_path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"Archive: {len(days)} day(s) recorded, {days[0]['d']} to {days[-1]['d']}.")

    # date_idx was filled in feed order; sort it so index order is chronological
    order_dates = sorted(range(len(dates)), key=lambda k: dates[k])
    remap = {old: new for new, old in enumerate(order_dates)}
    dates = [dates[k] for k in order_dates]
    remaining = [[remap[d], a, h] for d, a, h in remaining]
    played = [[remap[d], a, h, r] for d, a, h, r in played]
    remaining.sort(key=lambda g: g[0])
    played.sort(key=lambda g: g[0])

    keep = ("i", "id", "abbr", "name", "full", "city", "lg", "div", "divName", "w", "l",
            "pct", "pyth", "rs", "ra", "gp", "rem", "gb", "wcgb", "l10", "streak")
    out = {
        "lastGameDate": last_final,
        "prev": prev,
        # inlined so the page needs no second request and still works offline
        "hist": hist,
        "nAL": NAL,
        "dates": dates,
        "teams": [{k: m[k] for k in keep} for m in order],
        "games": remaining,
        "played": played,
        "h2h": h2h,
        "divrec": divrec,
        "learec": learec,
    }
    blob = json.dumps(out, separators=(",", ":"))

    # Refuse to write anything the page cannot use.
    if len(out["teams"]) != 30:
        sys.exit(f"ERROR: expected 30 teams, got {len(out['teams'])} — not writing")
    if not last_final:
        # Between seasons there is nothing to refresh. Leave the page as it is and
        # succeed, so the daily job does not fail and email you all winter.
        print(f"No completed {SEASON} games yet — nothing to refresh. Leaving index.html alone.")
        return

    html = open(PAGE, encoding="utf-8").read()
    i, j = html.find(START), html.find(END)
    if i < 0 or j < 0:
        sys.exit(f"ERROR: could not find the {START} / {END} markers in {PAGE}")
    new = (html[:i] + START
           + '<script id="mlb-data" type="application/json">' + blob + '</script>'
           + html[j:])
    changed = new != html
    open(PAGE, "w", encoding="utf-8").write(new)

    # Read it back and re-parse, so a broken write can never be committed.
    check = open(PAGE, encoding="utf-8").read()
    a = check.find('<script id="mlb-data" type="application/json">')
    b = check.find("</script>", a)
    if a < 0 or b < 0:
        sys.exit("ERROR: data block missing after write")
    reparsed = json.loads(check[a + len('<script id="mlb-data" type="application/json">'):b])
    if len(reparsed["teams"]) != 30 or reparsed["lastGameDate"] != last_final:
        sys.exit("ERROR: data block did not survive the write")

    fetch_logos(order)

    tor = next(m for m in al if m["abbr"] == "TOR")
    print(f"Games complete through {last_final}.")
    print(f"Blue Jays {tor['w']}-{tor['l']}, {tor['gb']} back in the East, "
          f"{tor['wcgb']} back of a wild card, {tor['rem']} games left.")
    print(f"{len(remaining)} remaining games involving an AL club.")
    print(f"Wrote {len(blob) / 1024:.1f} KB into index.html "
          f"({'changed' if changed else 'no change'}).")


if __name__ == "__main__":
    main()
