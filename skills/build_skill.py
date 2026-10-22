"""Copy the current quote engine, standing corrections and Devon calculator into the devon-quote skill
and package it for sharing.

    python skills/build_skill.py        ->  build/devon-quote.skill

The newest templates/DEVON*.xlsm is bundled as the default calculator. When Devon sends a new one (about
every 6 months), drop it in templates/ and run this again. The calculator stays out of git (.gitignore).
"""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "devon-quote"
SCRIPTS = SKILL / "scripts"
PACKAGE_FILES = ["__init__.py", "__main__.py", "bom.py", "catalog.py", "cli.py", "mapper.py", "marks.py",
                 "plan.py", "pricing.py", "report.py", "service.py", "writer.py"]


def build() -> Path:
    if SCRIPTS.exists():
        shutil.rmtree(SCRIPTS)
    (SCRIPTS / "devon_quote").mkdir(parents=True)
    for name in PACKAGE_FILES:
        shutil.copy2(ROOT / "devon_quote" / name, SCRIPTS / "devon_quote" / name)
    (SCRIPTS / "mappings").mkdir()
    shutil.copy2(ROOT / "mappings" / "overrides.csv", SCRIPTS / "mappings" / "overrides.csv")
    calcs = sorted((ROOT / "templates").glob("DEVON*.xlsm"), key=lambda p: p.stat().st_mtime)
    if not calcs:
        raise SystemExit("Put Devon's calculator (DEVON*.xlsm) in templates/ first.")
    (SCRIPTS / "templates").mkdir()
    shutil.copy2(calcs[-1], SCRIPTS / "templates" / calcs[-1].name)  # the engine picks it up from here
    out = ROOT / "build" / "devon-quote.skill"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, Path("devon-quote") / f.relative_to(SKILL))
    return out


if __name__ == "__main__":
    out = build()
    print(out)
    print("bundled calculator:", next((SCRIPTS / "templates").glob("*.xlsm")).name)
