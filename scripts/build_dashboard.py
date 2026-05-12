"""
build_dashboard.py
==================
Reads data/q3_volumes.json, renders templates/template.html.j2,
writes docs/index.html for GitHub Pages.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    data_path = root / "data" / "q3_volumes.json"
    template_dir = root / "templates"
    output_path = root / "docs" / "index.html"
    output_path.parent.mkdir(exist_ok=True, parents=True)

    if not data_path.exists():
        raise FileNotFoundError(f"{data_path} not found — run fetch_data.py first.")

    data = json.loads(data_path.read_text())
    meta = data["metadata"]

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("template.html.j2")

    now = datetime.now(timezone.utc)
    year_range = f"{meta['years'][0]}–{meta['years'][-1]}"

    html = template.render(
        production_json=json.dumps(data["production"]),
        commodities_json=json.dumps(data["commodities"]),
        regions_json=json.dumps(data["regions"]),
        year_range=year_range,
        build_date=now.strftime("%b %d, %Y"),
    )

    output_path.write_text(html)
    print(f"✓ Wrote {output_path} ({len(html):,} chars)")


if __name__ == "__main__":
    main()
