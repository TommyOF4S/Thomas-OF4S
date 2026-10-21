"""Translate an AIS Divi bill of materials (from CET) into Devon part numbers.

Order of precedence for each AIS line:
  1. mappings/overrides.csv - exact (or wildcard) AIS part -> Devon part(s). Anything you
     teach the tool goes here, and it always wins over the built-in rules.
  2. Built-in rules for the Divi panel system (panels, posts, power, worksurfaces,
     supports, storage).
  3. Anything left is reported as UNMAPPED so it is never silently dropped.

Every line also gets a status: "ok", "review" (mapped, but a person should confirm) or
"unmapped". The review report lists the reason for each review item.
"""

from __future__ import annotations

import csv
import fnmatch
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .bom import BomLine
from .catalog import Catalog
from .plan import PlanResult

# Devon panel heights, and the size code each connector family uses at that height.
DEVON_HEIGHTS = (39, 47, 53, 67, 85)
_CONNECTOR_CODES = {
    # height: (code A used by HMA130/HMA137/HMA128, code B used by HMP213/HMA224/HMC132/HMA199)
    39: ("39", "34"),
    47: ("47", "42"),
    53: ("53", "48"),
    67: ("67", "62"),
    85: ("85", "80"),
}
JOINT_WORDS = {"l": "corner", "tee": "3-way joint", "cross": "4-way joint", "ends": "free end",
               "angled": "angled joint", "other": "joint of 5+ panels"}
# A Divi height more than this many inches below the Devon height it rounds up to is flagged.
HEIGHT_TOLERANCE = 6


def connector(kind: str, height: int) -> str:
    a, b = _CONNECTOR_CODES[height]
    return {
        "2way": f"HMA130.{a}",
        "3way": f"HMA137.{a}",
        "4way": f"HMC132.{b}",
        "inline": f"HMP213.{b}",
        "change_height": f"HMA224.{b}",
        "finished_end": f"HMA128.{a}",
        "wall_start": f"HMA199.{b}",
    }[kind]


def devon_height(divi_height: int) -> tuple[int, str]:
    """Round a Divi panel height up to the next Devon height (never lose privacy)."""
    for h in DEVON_HEIGHTS:
        if divi_height <= h:
            note = ""
            if h - divi_height > HEIGHT_TOLERANCE:
                note = f'AIS {divi_height}"H rounds up to Devon {h}"H'
            return h, note
    return DEVON_HEIGHTS[-1], f'AIS {divi_height}"H is taller than any Devon panel; used 85"H'


@dataclass
class Mapping:
    source: BomLine
    targets: list[tuple[str, float]]  # (Devon part, quantity per AIS unit)
    status: str  # ok | review | unmapped
    note: str = ""
    rule: str = ""


@dataclass
class Override:
    pattern: str
    devon_part: str
    ratio: float
    note: str


@dataclass
class MapResult:
    mappings: list[Mapping]
    quantities: dict[str, int]  # Devon part -> quantity for the calculator
    sources: dict[str, list[str]]  # Devon part -> AIS parts that produced it
    auto_added: list[tuple[str, int, str]]
    warnings: list[str] = field(default_factory=list)
    plan: PlanResult | None = None
    plan_parts: list[tuple[str, str, int]] = field(default_factory=list)  # (joint kind, Devon part, qty)

    @property
    def review(self) -> list[Mapping]:
        return [m for m in self.mappings if m.status == "review"]

    @property
    def unmapped(self) -> list[Mapping]:
        return [m for m in self.mappings if m.status == "unmapped"]


def load_overrides(path: str | Path | None) -> list[Override]:
    if not path or not Path(path).exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pat = (row.get("ais_part") or "").strip()
            if not pat or pat.startswith("#"):
                continue
            out.append(
                Override(
                    pattern=pat.upper(),
                    devon_part=(row.get("devon_part") or "").strip(),
                    ratio=float(row.get("ratio") or 1),
                    note=(row.get("note") or "").strip(),
                )
            )
    return out


# --- built-in rules ---------------------------------------------------------------

_PANEL = re.compile(r"^P-DL([A-Z]+?)(\d{2})(\d{2})$")
_POST = re.compile(r"^P-DLPF([234])(\d{2})$")
_WS = re.compile(r"^W-WS(\d{2})(\d{2})$")
_CANT = re.compile(r"^WPS-UNCT(\d{2})([LRS])$")
_WIDTH = re.compile(r"(\d{2})\s*(?:\"|in\b|W\b)", re.I)


def _powered(desc: str) -> bool | None:
    d = desc.upper()
    if re.search(r"\bNPWR\b|NON-?POWER", d):
        return False
    if re.search(r"\bPWR\b|POWERED", d):
        return True
    return None


class Mapper:
    def __init__(self, catalog: Catalog, overrides: list[Override] | None = None):
        self.catalog = catalog
        self.overrides = overrides or []
        self.run_height: int | None = None  # dominant Devon panel height, for height-less parts
        self.plan: PlanResult | None = None  # joints read from the 2D plan, when one was given

    # Each rule returns a Mapping or None.
    def _rule_override(self, line: BomLine) -> Mapping | None:
        pn = line.part.upper()
        hits = [o for o in self.overrides if fnmatch.fnmatchcase(pn, o.pattern)]
        if not hits:
            return None
        exact = [o for o in hits if o.pattern == pn]
        hits = exact or hits
        targets = [(o.devon_part, o.ratio) for o in hits if o.devon_part]
        notes = "; ".join(o.note for o in hits if o.note)
        if not targets:
            return Mapping(line, [], "ok", notes or "no Devon equivalent needed (override)", "override")
        missing = [t for t, _ in targets if t not in self.catalog]
        if missing:
            return Mapping(line, targets, "review", f"override points at {', '.join(missing)}, which is not in the Devon calculator", "override")
        return Mapping(line, targets, "ok", notes, "override")

    def _rule_panel(self, line: BomLine) -> Mapping | None:
        m = _PANEL.match(line.part.upper())
        if not m or line.part.upper().startswith(("P-DLPF", "P-DLSEOR")):
            return None
        kind, h, w = m.group(1), int(m.group(2)), int(m.group(3))
        desc = line.description
        height, hnote = devon_height(h)
        notes = [hnote] if hnote else []
        powered = _powered(desc)
        if powered is None:
            powered = False
            notes.append("could not tell if this panel is powered; quoted non-powered")
        glass = "GLASS" in desc.upper() or kind.startswith("QG") or kind.startswith("G")
        if glass:
            if height == 39 or height == 47:
                notes.append(f'Devon glass-stacker panels start at 53"H; used 53"H')
                height = 53
            family = "HM51"
            if not kind.startswith("QG"):
                notes.append("AIS full/partial glass panel quoted as Devon panel + 14\" glass stacker")
        else:
            family = "HM01"
            if "HARD SURF" in desc.upper() or "TILE" in desc.upper():
                pass  # Devon panels are fabric; AIS hard-surface skins map to the fabric panel
        part = f"{family}.{height}{w:02d}" + (".P4" if powered else "")
        if part not in self.catalog:
            return Mapping(line, [], "unmapped", f'no Devon {height}"H x {w}"W {"powered " if powered else ""}{"glass " if glass else ""}panel ({part})', "panel")
        return Mapping(line, [(part, 1)], "review" if notes else "ok", "; ".join(notes), "panel")

    def _rule_post(self, line: BomLine) -> Mapping | None:
        pn = line.part.upper()
        m = _POST.match(pn)
        is_end = pn == "P-DLSEOR" or "END OF RUN" in line.description.upper()
        if self.plan is not None and (m or is_end):
            return Mapping(line, [], "ok", "connectors and finished ends are counted from the 2D plan", "plan")
        if m:
            ways, h = int(m.group(1)), int(m.group(2))
            height, hnote = devon_height(h)
            if ways == 2:
                part = connector("2way", height)
                note = (
                    "AIS 2-way post covers both straight runs and L-corners; Devon uses "
                    f"{connector('inline', height)} for straight panel-to-panel joints. Check the plan."
                )
                return Mapping(line, [(part, 1)], "review", "; ".join(filter(None, [hnote, note])), "post")
            part = connector("3way" if ways == 3 else "4way", height)
            return Mapping(line, [(part, 1)], "review" if hnote else "ok", hnote, "post")
        if is_end:
            height = self.run_height or 53
            note = f'finished end quoted at {height}"H (the main panel height in this BOM)'
            return Mapping(line, [(connector("finished_end", height), 1)], "review", note, "post")
        if "WALL START" in line.description.upper():
            height = self.run_height or 53
            return Mapping(line, [(connector("wall_start", height), 1)], "review", f'wall start quoted at {height}"H', "post")
        return None

    def _rule_electrical(self, line: BomLine) -> Mapping | None:
        if not line.part.upper().startswith("E-"):
            return None
        d = line.description.upper()
        if "FEED" in d:
            if "CEILING" in d:
                return Mapping(line, [("BE-CELFD", 1)], "ok", "", "electrical")
            if "POLE" in d:
                return Mapping(line, [("BE-PP12", 1)], "ok", "", "electrical")
            if "SIDE" in d:
                return Mapping(line, [("BE-SDFD1", 1)], "review", "AIS side-mounted base infeed quoted as Devon side feed (BE-SDFD1); use BE-ENDFD if it feeds the end of the run", "electrical")
            return Mapping(line, [("BE-ENDFD", 1)], "review", "AIS base infeed quoted as Devon end feed", "electrical")
        if "OUTLET" in d or "RECEPTACLE" in d or "DUPLEX" in d:
            m = re.search(r"(?:LINE|CIRCUIT|CKT)\s*(\d)", d)
            n = int(m.group(1)) if m else 1
            if n > 4:
                return Mapping(line, [("BE-REC4", 1)], "review", f"AIS circuit {n} has no Devon equivalent (4-circuit system); used circuit 4", "electrical")
            note = "" if m else "circuit not stated; used circuit 1"
            return Mapping(line, [(f"BE-REC{n}", 1)], "review" if note else "ok", note, "electrical")
        if "JUMPER" in d:
            return Mapping(
                line, [], "review",
                "Devon P4 panels connect power panel-to-panel, so AIS jumpers are not quoted; "
                "add a BE-xxJU pass-thru for each non-powered panel that sits between powered panels",
                "electrical",
            )
        if "DATA" in d:
            return Mapping(line, [("BE01439-C", 1)], "review", "AIS data plate quoted as Devon data window", "electrical")
        return None

    def _rule_worksurface(self, line: BomLine) -> Mapping | None:
        m = _WS.match(line.part.upper())
        if not m:
            return None
        depth, width = int(m.group(1)), int(m.group(2))
        part = f"WS{depth}{width:02d}"
        if part in self.catalog:
            return Mapping(line, [(part, 1)], "ok", "", "worksurface")
        # Next larger Devon size of the same depth, cut down.
        sizes = sorted(
            int(p[4:]) for p in self.catalog.items
            if re.fullmatch(rf"WS{depth}\d\d", p) and int(p[4:]) >= width
        )
        if sizes:
            bigger = f"WS{depth}{sizes[0]:02d}"
            return Mapping(line, [(bigger, 1), ("MIS-002", 1)], "review", f'no Devon {depth}x{width}; quoted {bigger} with custom-cut up-charge', "worksurface")
        return Mapping(line, [], "unmapped", f"no Devon {depth}x{width} worksurface", "worksurface")

    def _rule_support(self, line: BomLine) -> Mapping | None:
        pn = line.part.upper()
        m = _CANT.match(pn)
        if m:
            depth, hand = int(m.group(1)), m.group(2)
            size = "22" if depth >= 22 else "16"
            if hand == "S":
                return Mapping(line, [(f"HMP226.{size}", 1)], "ok", "", "support")
            # Devon sells cantilevers as L/R pairs: each AIS left or right counts as half a pair.
            pair = "HMP225.22" if size == "22" else "HMP165.16"
            return Mapping(line, [(pair, 0.5)], "ok", "", "support")
        if pn == "WPS-FP" or "FLAT PLATE" in line.description.upper():
            return Mapping(line, [("ACC-105", 1)], "ok", "", "support")
        if pn.startswith("WPS-VC"):
            part = pn[4:] if pn[4:] in self.catalog else None
            part = f"WPS-{pn[4:]}" if f"WPS-{pn[4:]}" in self.catalog else part
            if part:
                return Mapping(line, [(part, 1)], "ok", "", "support")
        if "CORNER BRACKET" in line.description.upper():
            return Mapping(line, [("HMP455.01-L", 0.5), ("HMP455.01-R", 0.5)], "review", "corner brackets split evenly left/right", "support")
        return None

    def _rule_storage(self, line: BomLine) -> Mapping | None:
        d = line.description.upper()
        pn = line.part.upper()
        if "PEDESTAL" in d or pn.startswith("S-PED"):
            if "MOBILE" in d or "MOB" in pn:
                part = "ECO-MOB BF"
            elif "F/F" in d or "FF" in pn.replace("BBF", ""):
                part = "ECO-FF-MT"
            else:
                part = "ECO-BBF-MT"
            return Mapping(line, [(part, 1)], "review", "AIS pedestal quoted as Devon ECO-style pedestal. Confirm size and finish.", "storage")
        if "LATERAL" in d:
            return Mapping(line, [("G-LF230", 1)], "review", "AIS lateral quoted as Devon 30\" 2-drawer lateral", "storage")
        width = _WIDTH.search(line.description)
        w = width.group(1) if width else None
        for key, prefix in (("BINDER", "HMU271"), ("OVERHEAD", "HMU271"), ("FULL HEIGHT SHELF", "HMA282"), ("SHELF", "HMA281")):
            if key in d and w and f"{prefix}.{w}" in self.catalog:
                return Mapping(line, [(f"{prefix}.{w}", 1)], "review", "", "storage")
        if "TACK" in d and w and f"TB{w}" in self.catalog:
            return Mapping(line, [(f"TB{w}", 1)], "ok", "", "storage")
        return None

    RULES = ("_rule_override", "_rule_panel", "_rule_post", "_rule_electrical", "_rule_worksurface", "_rule_support", "_rule_storage")

    def map_line(self, line: BomLine) -> Mapping:
        for name in self.RULES:
            m = getattr(self, name)(line)
            if m is not None:
                return m
        return Mapping(line, [], "unmapped", "no rule or override for this AIS part", "")

    def map(self, lines: list[BomLine], plan: PlanResult | None = None) -> MapResult:
        # Main panel height, used for parts that don't carry a height (end-of-run, wall start).
        heights = Counter()
        for ln in lines:
            m = _PANEL.match(ln.part.upper())
            if m and not ln.part.upper().startswith(("P-DLPF", "P-DLSEOR")):
                heights[devon_height(int(m.group(2)))[0]] += ln.qty
        self.run_height = heights.most_common(1)[0][0] if heights else None
        self.plan = plan if plan is not None and plan.panels else None

        mappings = [self.map_line(ln) for ln in lines]

        raw: dict[str, float] = defaultdict(float)
        sources: dict[str, list[str]] = defaultdict(list)
        for m in mappings:
            for part, ratio in m.targets:
                raw[part] += m.source.qty * ratio
                if m.source.part not in sources[part]:
                    sources[part].append(m.source.part)
        warnings = []
        plan_parts = []
        if self.plan is not None:
            plan_parts, plan_warnings = self._plan_connectors(lines, list(heights))
            warnings += plan_warnings
            for _, part, qty in plan_parts:
                raw[part] += qty
                if "2D plan" not in sources[part]:
                    sources[part].append("2D plan")
        quantities = {p: math.ceil(q - 1e-9) for p, q in raw.items() if q > 0}

        lefts = sum(m.source.qty for m in mappings if m.source.part.upper().endswith(("UNCT24L", "UNCT16L")))
        rights = sum(m.source.qty for m in mappings if m.source.part.upper().endswith(("UNCT24R", "UNCT16R")))
        if lefts != rights:
            warnings.append(f"AIS left cantilevers ({lefts:g}) and right cantilevers ({rights:g}) don't match; Devon sells them as pairs")

        auto_added = self._auto_add(quantities)
        return MapResult(mappings, quantities, dict(sources), auto_added, warnings, self.plan, plan_parts)

    def _height_changes(self, bom_heights: list[int], warnings: list[str]) -> tuple[Counter, Counter, int]:
        """Change-of-height kits and filler strips from the red dots on the plan."""
        kits, fillers, on_straight = Counter(), Counter(), 0
        for ch in self.plan.height_changes:
            where = f"the red dot on page {ch.page}" + (f' labeled "{ch.label}"' if ch.label else "")
            Where = where[0].upper() + where[1:]
            if ch.joint is None:
                warnings.append(f"{Where} isn't on a panel joint, so it was not quoted. Put the dot right on the joint.")
                continue
            if ch.heights:
                lo, hi = sorted(devon_height(h)[0] for h in ch.heights)
            elif len(bom_heights) == 2:
                lo, hi = sorted(bom_heights)
                warnings.append(f'{Where} has no height label; used the BOM\'s two heights, {lo}" and {hi}". Add a label like {lo}/{hi}.')
            else:
                warnings.append(f"{Where} has no height label like 47/53, so it was not quoted.")
                continue
            if lo == hi:
                warnings.append(f'{Where}: both heights are {lo}"H on Devon, so no change-of-height parts are needed.')
                continue
            if ch.joint == "straight":
                on_straight += 1
            else:
                warnings.append(f"{Where} sits on a {JOINT_WORDS.get(ch.joint, 'joint')}; Devon's change-of-height kit is "
                                "for straight runs. The kit and filler strip are quoted there; check it.")
            kits[connector("change_height", hi)] += 1
            filler = f"HMHL{lo}{hi}"
            if filler in self.catalog:
                fillers[filler] += 1
            else:
                warnings.append(f'Devon has no filler strip for {lo}" to {hi}" ({where}); add one by hand.')
        return kits, fillers, on_straight

    def _plan_connectors(self, lines: list[BomLine], bom_heights: list[int]) -> tuple[list[tuple[str, str, int]], list[str]]:
        """Devon connectors from the joints measured on the 2D plan, plus cross-checks against the BOM."""
        plan = self.plan
        height = self.run_height or 53
        c = plan.counts
        warnings = []
        kits, fillers, on_straight = self._height_changes(bom_heights, warnings)
        # A change-of-height kit includes the panel-to-panel connector for its joint.
        joint_qty = Counter(c)
        joint_qty["straight"] -= on_straight
        parts = [
            (kind, connector(devon_kind, height), joint_qty[kind])
            for kind, devon_kind in (("straight", "inline"), ("l", "2way"), ("tee", "3way"),
                                     ("cross", "4way"), ("ends", "finished_end"))
            if joint_qty[kind] > 0
        ]
        parts += [("change_height", p, q) for p, q in kits.items()]
        parts += [("filler", p, q) for p, q in fillers.items()]
        if len(bom_heights) > 1 and not plan.height_changes:
            warnings.append(f'The BOM has panels at more than one height; plan connectors are all quoted at {height}"H. '
                            "Mark each height change on the CET plan with a red dot and a label like 47/53 "
                            "to add the change-of-height kit (HMA224) and filler strip.")
        if c["angled"]:
            warnings.append(f"The 2D plan has {c['angled']} joint(s) at an angle other than 90 or 180 degrees. "
                            "Devon has no angled connector; check those runs.")
        if c["other"]:
            warnings.append(f"The 2D plan has {c['other']} joint(s) where more than four panels meet. Check those by hand.")

        # Cross-check the plan against the AIS BOM: they should be the same revision.
        bom = Counter()
        bom_widths = Counter()
        for ln in lines:
            pn = ln.part.upper()
            pm = _POST.match(pn)
            if pm:
                bom[f"pf{pm.group(1)}"] += ln.qty
            elif pn == "P-DLSEOR" or "END OF RUN" in ln.description.upper():
                bom["seor"] += ln.qty
            else:
                m = _PANEL.match(pn)
                if m:
                    bom["panels"] += ln.qty
                    bom_widths[int(m.group(3))] += ln.qty
        n = lambda k, word: f"{k} {word}" + ("" if k == 1 else "s")
        checks = [
            ("panels", plan.panels, n(plan.panels, "panel"), "panels"),
            ("pf2", c["straight"] + c["l"], f"{n(c['straight'], 'straight joint')} + {n(c['l'], 'corner')}", "2-way posts"),
            ("pf3", c["tee"], n(c["tee"], "three-way joint"), "3-way posts"),
            ("pf4", c["cross"], n(c["cross"], "four-way joint"), "4-way posts"),
            ("seor", c["ends"], n(c["ends"], "free end"), "end-of-run shrouds"),
        ]
        for key, plan_n, plan_text, bom_text in checks:
            if bom[key] and abs(bom[key] - plan_n) > 0:
                warnings.append(f"The 2D plan shows {plan_text}, but the AIS BOM has {bom[key]:g} {bom_text}. "
                                "Make sure the plan and the BOM are the same revision.")
        if bom_widths and plan.widths and bom_widths != plan.widths:
            fmt = lambda w: ", ".join(f'{n:g} x {k}"' for k, n in sorted(w.items()))
            warnings.append(f"Panel widths differ: the plan has {fmt(plan.widths)}; the BOM has {fmt(bom_widths)}.")
        return parts, warnings

    def _auto_add(self, q: dict[str, int]) -> list[tuple[str, int, str]]:
        """No-charge hardware Devon asks to be listed on every order."""
        added = []

        def add(part: str, qty: int, why: str):
            if qty > 0 and part in self.catalog and part not in q:
                q[part] = qty
                added.append((part, qty, why))

        count = lambda prefix: sum(v for k, v in q.items() if k.startswith(prefix))
        add("ACC-106", count("ECO-") + count("G-LF"), "fastener kit, one per pedestal/lateral")
        add("ACC-107", count("HMP165") + count("HMP166") + count("HMP225") + count("HMP226"), "fastener kit, one per cantilever item")
        add("ACC-108", count("HMP455"), "fastener kit, one per corner bracket")
        if any(k.startswith(("HM01", "HM51", "HM52", "HM61", "HM62")) for k in q):
            add("ACC-110", 1, "touch-up paint, one per panel order at no charge")
        return added
