"""Assemble the hosted page: hosted.html with the JS engine and the sample job inlined.

    python -m devon_quote.web.build_hosted   ->  build/devon_quote_builder.html

Publish that file as the claude.ai artifact (capabilities: db, user, downloads).
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "build" / "devon_quote_builder.html"

# Shared settings for the published page: everyone who can use the page reads the stored
# Devon calculator; only editors replace it. Corrections use the default rules
# (Contributors and up write).
CAPABILITIES = {
    "db": {"rules": [{"path": "config", "read": "interact", "write": "admin"}]},
    "user": {},
    "downloads": True,
}


def build() -> Path:
    page = (HERE / "hosted.html").read_text(encoding="utf-8")
    engine = (HERE / "engine.js").read_text(encoding="utf-8")
    sample = (ROOT / "tests" / "fixtures" / "sample_ais_divi.sif").read_text(encoding="utf-8")
    assert "</script" not in engine.lower()
    page = page.replace("/*__ENGINE__*/", engine, 1)
    page = page.replace('/*__SAMPLE__*/""', json.dumps(sample).replace("</", "<\\/"), 1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build())
    print("capabilities:", json.dumps(CAPABILITIES))
