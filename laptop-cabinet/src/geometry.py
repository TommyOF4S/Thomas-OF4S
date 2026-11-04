"""LC-60 laptop storage cabinet: single source of truth for every dimension.

Coordinate system (inches):
  x = width, 0 at the outside face of the LEFT side panel, increasing to the right
  y = depth, 0 at the FRONT face of the cabinet, increasing toward the wall
  z = height, 0 at the finished floor

Every drawing, render, DXF and cut list is generated from the values below.
Change a design input here, run build.py, and the whole package regenerates.
"""
from fractions import Fraction

# ---------------------------------------------------------------- design inputs
LAPTOP_W = 10.0        # laptop footprint, side to side (in)
LAPTOP_D = 14.0        # laptop footprint, front to back (in)
LAPTOP_T = 1.5         # laptop thickness (in)
STACK = 5              # laptops per stack (client limit)
LAPTOPS = 60           # required capacity

T = 1.0                # carcass panel thickness: sides, top, bottom, shelves, dividers
BACK_T = 0.5           # back panel thickness (captured in rabbet)
BASE_H = 4.0           # toe-kick base height (floor to underside of bottom deck)
KICK_SETBACK = 3.0     # toe kick recess from the front face
COLS = 4               # stacks side by side
TIERS = 3              # stacks one above the other
OPEN_W = 11.0          # clear opening width per bay  (laptop 10" + 1/2" each side)
OPEN_H = 9.0           # clear opening height per bay (stack 7-1/2" + 1-1/2" lift room)

# ---------------------------------------------------------------- derived sizes
W = 2 * T + COLS * OPEN_W + (COLS - 1) * T          # 49
H = BASE_H + T + TIERS * OPEN_H + (TIERS - 1) * T + T  # 35
D = 16.0
INT_W = W - 2 * T                                    # 47  (between sides)
INT_D = D - BACK_T                                   # 15.5 (front to back panel)
SIDE_H = H - T                                       # 34  (top sits on the sides)
STACK_H = STACK * LAPTOP_T                           # 7.5
BAYS = COLS * TIERS                                  # 12
CAPACITY = BAYS * STACK                              # 60
assert CAPACITY >= LAPTOPS, "design does not hold the required laptops"
assert abs(W - 49) < 1e-9 and abs(H - 35) < 1e-9

BOTTOM_Z = BASE_H                                    # underside of bottom deck = 4
FLOOR1_Z = BASE_H + T                                # first storage surface = 5


def tier_floor(t):
    """Top surface of the deck/shelf that tier t (0 = lowest) sits on."""
    return FLOOR1_Z + t * (OPEN_H + T)


def shelf_z(i):
    """Underside z of fixed shelf i (0 = lower shelf)."""
    return tier_floor(i) + OPEN_H


def col_x(c):
    """Left edge x of clear opening for column c (0 = left)."""
    return T + c * (OPEN_W + T)


def divider_x(i):
    """Left face x of vertical divider i (0..COLS-2)."""
    return col_x(i) + OPEN_W


# ---------------------------------------------------------------- formatting
def fmt(x, inch=True):
    """49.5 -> 49-1/2"   0.5 -> 1/2"   (nearest 1/16)."""
    neg = x < 0
    x = abs(x)
    whole = int(x + 1e-9)
    frac = Fraction(x - whole).limit_denominator(16)
    if frac == 1:
        whole, frac = whole + 1, Fraction(0)
    if whole and frac:
        s = f"{whole}-{frac.numerator}/{frac.denominator}"
    elif frac:
        s = f"{frac.numerator}/{frac.denominator}"
    else:
        s = f"{whole}"
    return ("-" if neg else "") + s + ('"' if inch else "")


# ---------------------------------------------------------------- materials
MATERIALS = {
    "M1": {
        "name": '1" industrial particleboard core, thermally fused laminate (TFM) both faces',
        "short": '1" TFM board',
        "thk": 1.0,
        "psf": 3.9,  # approx. lb per sq ft
    },
    "M2": {
        "name": '1/2" MDF, TFM both faces (interior face to match carcass)',
        "short": '1/2" TFM back',
        "thk": 0.5,
        "psf": 2.1,
    },
}
EDGEBAND = "3 mm PVC, color-matched, radiused 1/16\" (≈ 1 mm)"

# ---------------------------------------------------------------- parts
# eb = list of edges banded, each "L1", "L2" (long edges) or "W1", "W2" (short edges)
# eb_len = banded length per piece (inches)
PARTS = [
    dict(mark="P01", name="Top", qty=1, L=W, Wd=D, mat="M1",
         eb=["L1", "L2", "W1", "W2"], eb_len=2 * W + 2 * D,
         notes="Sits on top of side panels. Flush front, back and ends. Band all 4 edges."),
    dict(mark="P02", name="Side panel (left & right, mirror pair)", qty=2, L=SIDE_H, Wd=D, mat="M1",
         eb=["front", "rear", "notch"], eb_len=(SIDE_H - BASE_H) + KICK_SETBACK + BASE_H + SIDE_H,
         notes=f'Toe-kick notch {fmt(KICK_SETBACK)} deep x {fmt(BASE_H)} high at front bottom. '
               f'{fmt(BACK_T)} x {fmt(BACK_T)} rabbet full height on rear inside edge for back panel. '
               "Make one left and one right."),
    dict(mark="P03", name="Bottom deck", qty=1, L=INT_W, Wd=INT_D, mat="M1",
         eb=["L1"], eb_len=INT_W,
         notes=f"Between sides, top surface at {fmt(FLOOR1_Z)} AFF. Band front edge."),
    dict(mark="P04", name="Fixed shelf", qty=TIERS - 1, L=INT_W, Wd=INT_D, mat="M1",
         eb=["L1"], eb_len=INT_W,
         notes="Fixed (not adjustable). Supported by dividers below every 12\". Band front edge."),
    dict(mark="P05", name="Vertical divider", qty=(COLS - 1) * TIERS, L=OPEN_H, Wd=INT_D, mat="M1",
         eb=["W1"], eb_len=OPEN_H,
         notes="Grain/length vertical. 3 per tier, stacked in line. Band front edge."),
    dict(mark="P06", name="Toe kick", qty=1, L=INT_W, Wd=BASE_H, mat="M1",
         eb=[], eb_len=0,
         notes=f"Between sides, front face recessed {fmt(KICK_SETBACK)} (flush with notch)."),
    dict(mark="P07", name="Rear base rail", qty=1, L=INT_W, Wd=BASE_H, mat="M1",
         eb=[], eb_len=0,
         notes="Between sides under rear of bottom deck, back face flush with back of deck."),
    dict(mark="P08", name="Back panel", qty=1, L=INT_W + 2 * BACK_T,
         Wd=H - T - BASE_H, mat="M2", eb=[], eb_len=0,
         notes="Captured in side rabbets, screwed to rear edges of deck, shelves and dividers "
               "#6 x 5/8\" pan head at 6\" o.c."),
]
PART_BY_MARK = {p["mark"]: p for p in PARTS}

for p in PARTS:
    p["T"] = MATERIALS[p["mat"]]["thk"]
    p["sqft_each"] = p["L"] * p["Wd"] / 144.0
    p["sqft_total"] = p["sqft_each"] * p["qty"]
    p["lb_total"] = p["sqft_total"] * MATERIALS[p["mat"]]["psf"]

# ---------------------------------------------------------------- 3D instances
# box = (x0, y0, z0, x1, y1, z1); side panels carry a (y, z) profile extruded along x.
SIDE_PROFILE = [  # (y, z) going round the side panel outline
    (KICK_SETBACK, 0), (D, 0), (D, SIDE_H), (0, SIDE_H), (0, BASE_H), (KICK_SETBACK, BASE_H)
]

INSTANCES = []


def _add(mark, box, label=None, **kw):
    INSTANCES.append(dict(mark=mark, box=[round(v, 4) for v in box], label=label, **kw))


_add("P01", (0, 0, SIDE_H, W, D, H), "Top")
_add("P02", (0, 0, 0, T, D, SIDE_H), "Side L", profile=SIDE_PROFILE)
_add("P02", (W - T, 0, 0, W, D, SIDE_H), "Side R", profile=SIDE_PROFILE)
_add("P03", (T, 0, BASE_H, W - T, INT_D, BASE_H + T), "Bottom deck")
for i in range(TIERS - 1):
    z = shelf_z(i)
    _add("P04", (T, 0, z, W - T, INT_D, z + T), f"Shelf {i + 1}")
for t in range(TIERS):
    for i in range(COLS - 1):
        x = divider_x(i)
        z = tier_floor(t)
        _add("P05", (x, 0, z, x + T, INT_D, z + OPEN_H), f"Divider t{t + 1}-{i + 1}", tier=t)
_add("P06", (T, KICK_SETBACK, 0, W - T, KICK_SETBACK + T, BASE_H), "Toe kick")
_add("P07", (T, INT_D - T, 0, W - T, INT_D, BASE_H), "Rear rail")
_add("P08", (T - BACK_T, INT_D, BASE_H, W - T + BACK_T, D, SIDE_H), "Back")

# laptop stacks: centered side to side, centered front to back in the 15-1/2" depth
LAPTOP_Y0 = (INT_D - LAPTOP_D) / 2  # 0.75
STACKS = []
for t in range(TIERS):
    for c in range(COLS):
        x0 = col_x(c) + (OPEN_W - LAPTOP_W) / 2
        STACKS.append(dict(col=c, tier=t, id=f"{'ABCD'[c]}{t + 1}",
                           box=[x0, LAPTOP_Y0, tier_floor(t), x0 + LAPTOP_W, LAPTOP_Y0 + LAPTOP_D,
                                tier_floor(t) + STACK_H]))

# ---------------------------------------------------------------- hardware
GLIDE_Y = [KICK_SETBACK + 1.5, D - 1.5]
HARDWARE = [
    dict(mark="H01", item="Leveling glide, 5/16\"-18, 1-1/4\" dia. nylon base, with threaded insert",
         qty=4, notes="Into bottom edge of each side panel, 2 per side. Adds about 3/8\" (see note 6)."),
    dict(mark="H02", item="8 mm x 35 mm fluted hardwood dowel", qty=2 * 2 * (COLS - 1) * TIERS + 2 * 2 * 6,
         notes="Divider ends (2 per end) and carcass joints. Glued."),
    dict(mark="H03", item="7 x 50 mm confirmat screw (or cam + bolt if shipped knock-down)", qty=36,
         notes="Sides to top, bottom deck, shelves, toe kick and rear rail. Heads capped."),
    dict(mark="H04", item="Confirmat cover cap, color-matched", qty=36, notes="Exposed screw heads on side panels."),
    dict(mark="H05", item="#6 x 5/8\" pan-head screw", qty=40, notes="Back panel to rabbets and rear edges, 6\" o.c."),
    dict(mark="H06", item="Anti-tip wall bracket kit (pair) with fasteners", qty=1,
         notes="Under top at rear. Required: loaded weight about 475 lb."),
    dict(mark="H07", item=EDGEBAND, qty=None, notes="See cut list for linear feet."),
]

# ---------------------------------------------------------------- alternates (priced separately)
DOOR_GAP = 0.125
DOOR_T = 0.75
DOOR_W = W / COLS - DOOR_GAP
DOOR_H = SIDE_H - BASE_H - DOOR_GAP
ALTERNATES = [
    dict(mark="ALT-1", title="Lockable doors",
         desc=f"4 full-overlay doors, one per column, {fmt(DOOR_W)} W x {fmt(DOOR_H)} H x {fmt(DOOR_T)} TFM, "
              "3 mm PVC all edges. 2 concealed 110° soft-close hinges per door (half-overlay on dividers). "
              "1 keyed-alike cam lock per door, 1 wire pull per door (4\" c.c.). Adds 3/4\" to depth."),
    dict(mark="ALT-2", title="Ventilation",
         desc="One 2\" dia. grommet hole with cap through the back panel at each bay (12), "
              "or 3 x 1/2\" x 6\" routed vent slots per bay. Needed if laptops go in warm."),
    dict(mark="ALT-3", title="Charging",
         desc="Not in base scope. If laptops must charge inside, quote a UL-listed charging "
              "solution separately (power strips inside casework are not code-compliant)."),
    dict(mark="ALT-4", title="Mobile base",
         desc="Replace toe kick and rear rail with a 1\" sub-base on 4 x 3\" locking casters, "
              "keeping 35\" overall height."),
    dict(mark="ALT-5", title="Bay labels",
         desc="Engraved or printed bay ID plates A1 to D3 on shelf fronts, 12 total."),
]

TOTAL_EB_IN = sum(p["eb_len"] * p["qty"] for p in PARTS)
TOTAL_LB = sum(p["lb_total"] for p in PARTS)
LAPTOP_LB_EACH = 5.0
LOADED_LB = TOTAL_LB + LAPTOPS * LAPTOP_LB_EACH


def to_json():
    return dict(
        W=W, D=D, H=H, T=T, BACK_T=BACK_T, BASE_H=BASE_H, KICK_SETBACK=KICK_SETBACK,
        COLS=COLS, TIERS=TIERS, OPEN_W=OPEN_W, OPEN_H=OPEN_H, INT_D=INT_D,
        LAPTOP=dict(w=LAPTOP_W, d=LAPTOP_D, t=LAPTOP_T, stack=STACK),
        instances=INSTANCES, stacks=STACKS,
        parts=[{k: p[k] for k in ("mark", "name", "qty", "L", "Wd", "T", "mat")} for p in PARTS],
        door=dict(w=DOOR_W, h=DOOR_H, t=DOOR_T, gap=DOOR_GAP),
    )


if __name__ == "__main__":
    print(f"W {W}  D {D}  H {H}  capacity {CAPACITY}")
    for p in PARTS:
        print(p["mark"], p["name"], p["qty"], fmt(p["L"]), fmt(p["Wd"]), fmt(p["T"]),
              f'{p["sqft_total"]:.1f} sf', f'{p["lb_total"]:.0f} lb')
    print("edgeband LF", TOTAL_EB_IN / 12, "empty lb", TOTAL_LB, "loaded lb", LOADED_LB)
