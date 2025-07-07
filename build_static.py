# Purpose: Render the demo-mode Flask site to pure HTML in docs/ for GitHub Pages.
from pathlib import Path
import re, shutil
from bs4 import BeautifulSoup  # pip install beautifulsoup4
from main import app           # your existing Flask app

# === CONFIG ==============================================================
OUTPUT_DIR = Path("docs")                    # final static folder
ROUTES = ["/"]          # only the main page
BASE_PATH = "/AIJobMatcher/"   # unchanged

# ========================================================================

def rewrite_links(html: str) -> str:
    """Convert absolute '/static/...' and '/<path>' links into ones that work
    from /AIJobMatcher/ on GitHub Pages."""
    soup = BeautifulSoup(html, "html.parser")

    # fix <link>, <script>, <img>, etc. → static assets
    for tag, attr in [("link", "href"), ("script", "src"), ("img", "src")]:
        for el in soup.find_all(tag):
            url = el.get(attr)
            if not url:
                continue
            if url.startswith("/static/"):
                el[attr] = f"{BASE_PATH}static/{url.split('/static/',1)[1]}"
            elif url.startswith("/") and not url.startswith("//"):
                # internal SPA links like "/jobs/remote"
                el[attr] = f"{BASE_PATH}{url.lstrip('/')}"
    return str(soup)

def main() -> None:
    # fresh build folder
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # copy /static exactly as-is
    shutil.copytree("static", OUTPUT_DIR / "static")

    with app.test_client() as client:
        for route in ROUTES:
            resp = client.get(route)
            if resp.status_code != 200:
                print(f"WARNING {route}: {resp.status_code}")
                continue

            html = resp.get_data(as_text=True)
            html = rewrite_links(html)

            # map "/" → index.html, "/jobs/remote" → jobs/remote/index.html
            out_path = OUTPUT_DIR / ("index.html" if route == "/" else f"{route.lstrip('/')}/index.html")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(html, encoding="utf-8")
            print("✓", route, "→", out_path)

    print("\nStatic demo written to", OUTPUT_DIR.resolve())

if __name__ == "__main__":
    main()
