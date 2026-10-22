"""Reproduce the calculator's totals so the review report can show the number up front."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import Catalog

# Delivery estimate from the order weight, fitted to 25 Devon quotes to OF4S (33010), Aug 2024 - Oct 2026:
# freight ~ $445 + $0.27/lb (R^2 0.96, typical miss about $110). Devon confirms the real figure.
DELIVERY_BASE = 445.0
DELIVERY_PER_LB = 0.27


def estimate_delivery(weight: float) -> float:
    """Estimated Devon delivery charge for an order of this many pounds, rounded to $5."""
    if weight <= 0:
        return 0.0
    return math.floor((DELIVERY_BASE + DELIVERY_PER_LB * weight) / 5 + 0.5) * 5.0


@dataclass
class PricedLine:
    part: str
    description: str
    qty: int
    list_each: float
    net_each: float
    weight: float

    @property
    def net_ext(self) -> float:
        return self.net_each * self.qty

    @property
    def list_ext(self) -> float:
        return self.list_each * self.qty


@dataclass
class Estimate:
    lines: list[PricedLine]
    list_total: float
    product_net: float
    surcharge: float
    delivery: float
    total: float
    weight: float
    stations: int | None
    delivery_auto: bool = False  # delivery was estimated from the weight, not entered

    @property
    def per_station(self) -> float | None:
        return self.total / self.stations if self.stations else None


def estimate(catalog: Catalog, quantities: dict[str, int], grade: int, delivery: float | None, stations: int | None) -> Estimate:
    """delivery=None estimates it from the order weight."""
    lines = []
    for part, qty in quantities.items():
        item = catalog.items[part]
        lp = item.list_price(grade)
        lines.append(PricedLine(part, item.description, qty, lp, lp * catalog.net_multiplier, item.weight * qty))
    lines.sort(key=lambda l: catalog.items[l.part].row)
    product = sum(l.net_ext for l in lines)
    surcharge = product * catalog.surcharge_rate
    weight = sum(l.weight for l in lines)
    auto = delivery is None
    if auto:
        delivery = estimate_delivery(weight)
    return Estimate(
        lines=lines,
        list_total=sum(l.list_ext for l in lines),
        product_net=product,
        surcharge=surcharge,
        delivery=delivery,
        total=product + surcharge + delivery,
        weight=weight,
        stations=stations,
        delivery_auto=auto,
    )
