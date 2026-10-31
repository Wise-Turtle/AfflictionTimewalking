# Affliction Timewalking

A timeline of Affliction Redux (Arugal) raid progression, from Molten Core to Siege of Orgrimmar, with achievements computed from the data.

- `index.html`: the page. A single self-contained file; open it in a browser or host it on GitHub Pages.
- `wcl_timewalking.py`: pulls the guild's reports from the Warcraft Logs Classic API and prints the `data:{...}` block to paste into `GUILDS` in `index.html`.

## Updating the data
1. `pip install requests`
2. Create an API client at https://classic.warcraftlogs.com/api/clients
3. Set `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in your terminal (never commit them).
4. `python wcl_timewalking.py` (guild ID defaults to 494079).
5. Paste the printed block over the `data:{...}` for the guild in `index.html`.

## Hosting on GitHub Pages
Repo Settings > Pages > Deploy from branch > `main` / root.
