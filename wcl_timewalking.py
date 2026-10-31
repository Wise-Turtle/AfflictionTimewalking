#!/usr/bin/env python3
"""
Builds the `data:{...}` block for the Affliction Timewalking page from the
Warcraft Logs Classic API.

Setup
  1. pip install requests
  2. Create an API client at https://classic.warcraftlogs.com/api/clients
     (any name; redirect URL can be https://localhost)
  3. export WCL_CLIENT_ID=...   export WCL_CLIENT_SECRET=...
     (Windows PowerShell: $env:WCL_CLIENT_ID="...")

Run
  python wcl_timewalking.py                # Affliction Redux (guild 494079)
  python wcl_timewalking.py 123456         # another guild ID
  python wcl_timewalking.py 494079 --no-ranks

Output
  Prints the data block and writes it to wcl_data_<guildID>.js.
  Paste it over `data:{}` for that guild in the page's GUILDS object,
  or send it to Claude to publish.
"""
import os, re, sys, json, time
from datetime import datetime, timezone
import requests

BASE = "https://classic.warcraftlogs.com"
TOKEN_URL = BASE + "/oauth/token"
API_URL = BASE + "/api/v2/client"

# zone name (lowercase letters only) -> tier id used by the page
ZONE_TO_TIER = {
    "moltencore": "mc", "onyxiaslair": "mc",
    "blackwinglair": "bwl",
    "zulgurub": "zg", "ruinsofahnqiraj": "zg",
    "templeofahnqiraj": "aq",
    "karazhan": "kara", "gruulslair": "kara", "magtheridonslair": "kara",
    "serpentshrinecavern": "ssc", "tempestkeep": "ssc",
    "hyjalsummit": "bt", "blacktemple": "bt",
    "sunwellplateau": "swp",
    "eyeofeternity": "nax2", "obsidiansanctum": "nax2",
    "ulduar": "uld",
    "trialofthecrusader": "toc", "onyxiaslairwrath": "toc",
    "icecrowncitadel": "icc", "rubysanctum": "icc",
    "blackwingdescent": "bwd", "thebastionoftwilight": "bwd",
    "bastionoftwilight": "bwd", "thethroneofthefourwinds": "bwd",
    "throneofthefourwinds": "bwd",
    "firelands": "fl",
    "dragonsoul": "ds",
    "mogushanvaults": "msv", "heartoffear": "msv", "terraceofendlessspring": "msv",
    "throneofthunder": "tot",
    "siegeoforgrimmar": "soo",
    # Warcraft Logs combined zone names
    "gruulmagtheridon": "kara",
    "ssctk": "ssc",
    "bthyjal": "bt",
    "naxxsarthmaly": "nax2",
    "totfwbwdbot": "bwd",
    "hoftoes": "msv",
}
# Naxxramas exists twice (Classic 2019-21, Wrath 2022+); split by report year
NAXX_SPLIT = datetime(2022, 9, 26, tzinfo=timezone.utc)  # Wrath Classic launch


def key(name):
    return re.sub(r"[^a-z]", "", name.lower())


def get_token():
    cid, sec = os.environ.get("WCL_CLIENT_ID"), os.environ.get("WCL_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("Set WCL_CLIENT_ID and WCL_CLIENT_SECRET first (see top of file).")
    r = requests.post(TOKEN_URL, data={"grant_type": "client_credentials"}, auth=(cid, sec), timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def gql(token, query, variables=None):
    for attempt in range(4):
        r = requests.post(API_URL, json={"query": query, "variables": variables or {}},
                          headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1)); continue
        r.raise_for_status()
        j = r.json()
        if "errors" in j:
            raise RuntimeError(j["errors"][0]["message"])
        return j["data"]
    raise RuntimeError("Rate limited too many times; try again later.")


def tier_for(zone_name, dt):
    k = key(zone_name)
    if k == "naxxramas":
        return "naxx" if dt < NAXX_SPLIT else "nax2"
    if k == "onyxia":
        return "mc" if dt < NAXX_SPLIT else "toc"
    return ZONE_TO_TIER.get(k)


def fetch_reports(token, guild_id):
    q = """query($g:Int,$p:Int){reportData{reports(guildID:$g,page:$p,limit:100){
             has_more_pages data{code title startTime zone{id name}}}}}"""
    out, page = [], 1
    while True:
        d = gql(token, q, {"g": guild_id, "p": page})["reportData"]["reports"]
        out += d["data"]
        print(f"  reports page {page}: {len(d['data'])}", file=sys.stderr)
        if not d["has_more_pages"]:
            return out
        page += 1


def has_kill(token, code):
    q = """query($c:String){reportData{report(code:$c){fights(killType:Kills){id}}}}"""
    f = gql(token, q, {"c": code})["reportData"]["report"]["fights"]
    return bool(f)


def fetch_rank(token, guild_id, zone_id):
    q = """query($g:Int,$z:Int){guildData{guild(id:$g){zoneRanking(zoneId:$z){
             progress{worldRank{number} regionRank{number} serverRank{number}}}}}}"""
    try:
        zr = gql(token, q, {"g": guild_id, "z": zone_id})["guildData"]["guild"]["zoneRanking"]
        p = (zr or {}).get("progress") or {}
        n = (p.get("serverRank") or {}).get("number")
    except Exception:
        return None
    return f"Realm #{n}" if n else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    guild_id = int(args[0]) if args else 494079
    want_ranks = "--no-ranks" not in sys.argv

    token = get_token()
    print(f"Fetching reports for guild {guild_id}...", file=sys.stderr)
    reports = [r for r in fetch_reports(token, guild_id) if r.get("zone")]
    reports.sort(key=lambda r: r["startTime"])

    tiers = {}      # tier id -> {"kill":..., "zones":set(zoneIDs), "code":...}
    unmapped = set()
    for r in reports:
        dt = datetime.fromtimestamp(r["startTime"] / 1000, tz=timezone.utc)
        t = tier_for(r["zone"]["name"], dt)
        if not t:
            unmapped.add(r["zone"]["name"]); continue
        e = tiers.setdefault(t, {"kill": None, "zones": set(), "checked": 0, "n": 0})
        e["n"] += 1
        e["zones"].add(r["zone"]["id"])
        if e["kill"] is None and e["checked"] < 60:   # cap API calls per tier
            e["checked"] += 1
            if has_kill(token, r["code"]):
                e["kill"] = dt.strftime("%Y-%m-%d")

    print("\nTier summary (reports found / with a kill):", file=sys.stderr)
    for t in ["mc","bwl","zg","aq","naxx","kara","ssc","bt","swp","nax2","uld","toc","icc",
              "bwd","fl","ds","msv","tot","soo"]:
        e = tiers.get(t)
        if not e:
            print(f"  {t:5} no reports found", file=sys.stderr)
        else:
            print(f"  {t:5} {e['n']} reports, kill: {e['kill'] or 'none found'}", file=sys.stderr)

    data = {}
    for t, e in tiers.items():
        if not e["kill"]:
            continue
        entry = {"kill": e["kill"]}
        if want_ranks:
            ranks = [x for x in (fetch_rank(token, guild_id, z) for z in e["zones"]) if x]
            if ranks:
                entry["rank"] = min(ranks, key=lambda s: int(s.split("#")[1]))
        data[t] = entry

    block = "data:" + json.dumps(data, indent=2)
    path = f"wcl_data_{guild_id}.js"
    with open(path, "w") as f:
        f.write(block + "\n")
    print(block)
    print(f"\nWrote {path}", file=sys.stderr)
    if unmapped:
        print("Zones not mapped to a tier (ignored): " + ", ".join(sorted(unmapped)), file=sys.stderr)


if __name__ == "__main__":
    main()
