"""Package only public site assets for GitHub Pages. No dependencies required."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "_site"
ASSETS = ("index.html", "styles.css", "app.js", "locations.js")


def main():
    # Start with an empty output directory so old files cannot leak into a deploy.
    if DESTINATION.exists():
        shutil.rmtree(DESTINATION)
    DESTINATION.mkdir()
    for name in ASSETS:
        shutil.copyfile(ROOT / name, DESTINATION / name)

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    locations = (ROOT / "locations.js").read_text(encoding="utf-8")
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="styles.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<script src="locations.js" defer></script>', "")
    html = html.replace('<script src="app.js" defer></script>', "")
    html = html.replace("</body>", f"<script>\n{locations}\n{app}\n</script>\n</body>")
    (DESTINATION / "embervale-atlas.html").write_text(html, encoding="utf-8")
    (DESTINATION / ".nojekyll").touch()
    print(f"Packaged {len(ASSETS) + 2} public files in {DESTINATION}")


if __name__ == "__main__":
    main()
