"""Reproduce the calculator's totals so the review report can show the number up front."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog


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

    @property
    def per_station(self) -> float | None:
        return self.total / self.stations if self.stations else None


def estimate(catalog: Catalog, quantities: dict[str, int], grade: int, delivery: float, stations: int | None) -> Estimate:
    lines = []
    for part, qty in quantities.items():
        item = catalog.items[part]
        lp = item.list_price(grade)
        lines.append(PricedLine(part, item.description, qty, lp, lp * catalog.net_multiplier, item.weight * qty))
    lines.sort(key=lambda l: catalog.items[l.part].row)
    product = sum(l.net_ext for l in lines)
    surcharge = product * catalog.surcharge_rate
    return Estimate(
        lines=lines,
        list_total=sum(l.list_ext for l in lines),
        product_net=product,
        surcharge=surcharge,
        delivery=delivery,
        total=product + surcharge + delivery,
        weight=sum(l.weight for l in lines),
        stations=stations,
    )
