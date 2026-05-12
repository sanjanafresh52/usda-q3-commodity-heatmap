# Q3 Reefer Volume Heat Map — USDA AMS

Automated US heat map of Q3 (July–September) refrigerated truck fruit & vegetable volumes by USDA shipping region. Data is pulled live from the USDA AMS Specialty Crops Movement Reports (Socrata dataset `rfpn-7etz`, the same source your original chart was built from). The dashboard publishes to GitHub Pages — perfect for embedding in your Q3 customer report.

**Live URL:** `https://<your-username>.github.io/<repo-name>/`

---

## Setup (5 minutes)

1. **Push this repo to GitHub.**
2. **Settings → Pages → Source: GitHub Actions.**
3. *(Optional)* **Settings → Secrets → Actions → New repository secret** named `SOCRATA_APP_TOKEN` if you have one. Not required — the AMS dataset is public — but a token raises your rate limit. Free token here: https://data.socrata.com/profile/app_tokens
4. **Actions → Build Q3 Dashboard → Run workflow.**

After ~90 seconds the heat map publishes at your Pages URL. Embed that URL in your Q3 report (iframe) or print → save as PDF for attachment.

---

## What it does

1. Pulls every Q3 (Jul/Aug/Sep) row from the **AMS Refrigerated Truck Volumes** dataset for the last 4 complete calendar years.
2. Aggregates by **commodity × USDA shipping region** (Arizona, California, Colorado, Florida, Great Lakes, Mid-Atlantic, New York, PNW, Southeast, Texas, plus Mexico-AZ / -CA / -NM / -TX crossings).
3. Renders a **choropleth US map** (Census Bureau state boundaries via TopoJSON, Albers projection) with a light-cream → dark-burnt-orange ramp.
4. **Two filters:** commodity (top 20 by volume + "All Commodities" rollup) and Q3 month (Full Q3 / Jul / Aug / Sep). Map recolors on each change.
5. **Hover** any state for `{state} · {region} · {volume}`. Hover Mexico boxes for cross-border volumes.

The dashboard auto-detects the dataset's column names on first request, so it stays working if AMS renames a field.

---

## Repo layout

```
.github/workflows/build.yml   Manual-trigger workflow → deploys to Pages
scripts/fetch_data.py         AMS Socrata API client; writes data/q3_volumes.json
scripts/build_dashboard.py    Jinja2 render → docs/index.html
templates/template.html.j2    Map + controls (D3 + TopoJSON, no other UI)
data/q3_volumes.json          Latest cached fetch
docs/index.html               Generated dashboard (published)
requirements.txt              requests + jinja2
```

---

## Local development

```bash
pip install -r requirements.txt
python scripts/fetch_data.py     # pulls fresh data
python scripts/build_dashboard.py # renders HTML
# Open docs/index.html
```

---

## Customization

- **Change region → state mapping:** edit `STATE_TO_REGION` near the top of the `<script>` in `templates/template.html.j2`.
- **Restyle:** all colors are CSS variables at the top of the template (`--heat-0` … `--heat-7`).
- **Add more commodities:** the script keeps the top 20 by volume; bump that in `fetch_data.py` if you want more (search for `[:20]`).
- **Different time window:** change `N_YEARS` or `Q3_MONTHS` in `fetch_data.py`.

---

## Data source

- **Dataset:** USDA AMS Specialty Crops Program — Refrigerated Truck Volumes
- **URL:** https://agtransport.usda.gov/Truck/Refrigerated-Truck-Volumes/rfpn-7etz
- **Owner:** Jesse Gastelle (AMS Transportation Services Division)
- **Updated:** weekly
- **API:** Socrata SODA v2 — `https://agtransport.usda.gov/resource/rfpn-7etz.json`
- **Units:** AMS publishes volumes in tons; the script converts to pounds for display.
