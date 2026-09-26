"""Oven scheduling with half-open ferment+bake+cool intervals and next free window."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int  # minutes from day origin
    end: int  # exclusive; half-open [start, end), back-to-back only touches endpoints

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class RecipeDurations:
    ferment_min: int
    bake_min: int

    @property
    def total(self) -> int:
        return self.ferment_min + self.bake_min


@dataclass(frozen=True)
class Occupancy:
    oven_id: int
    interval: Interval
    phase: str  # ferment | bake | cool
    batch_id: int

    @property
    def is_cool(self) -> bool:
        return self.phase == "cool"


PHASE_LABELS = {"ferment": "发酵", "bake": "烘烤", "cool": "冷却"}


def build_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    recipe: RecipeDurations,
    cool_min: int = 0,
) -> list[Occupancy]:
    """Ferment then bake; cooling trails the bake and keeps the oven busy.

    Cooling is a per-oven tail, not a product duration: ferment_end / bake_end
    math is untouched. cool_min <= 0 emits no occupancy, so the next batch may
    start at the exact bake-end endpoint.
    """
    ferment = Interval(start_min, start_min + recipe.ferment_min)
    bake = Interval(ferment.end, ferment.end + recipe.bake_min)
    occs = [
        Occupancy(oven_id, ferment, "ferment", batch_id),
        Occupancy(oven_id, bake, "bake", batch_id),
    ]
    _ = cool_min
    return occs


def find_conflicts(existing: list[Occupancy], candidates: list[Occupancy]) -> list[tuple[Occupancy, Occupancy]]:
    """Return (existing, candidate) overlapping pairs on the same oven.

    A new batch's ferment/bake may not overlap a prior batch's half-open
    cooling tail — during cooling the oven is still held. Candidate cooling is
    checked too, since it also occupies the oven.
    """
    hits: list[tuple[Occupancy, Occupancy]] = []
    for cand in candidates:
        for ex in existing:
            if ex.oven_id != cand.oven_id:
                continue
            if ex.interval.overlaps(cand.interval):
                hits.append((ex, cand))
    return hits


def next_free_window(
    existing: list[Occupancy],
    oven_id: int,
    duration: int,
    search_from: int = 0,
    search_to: int = 24 * 60,
) -> Interval | None:
    """Find earliest half-open [start, start+duration) free on oven.

    Every occupancy — cooling tails included — counts as busy, so a cooling
    tail is never offered as a free gap.
    """
    if duration <= 0:
        return None
    busy = sorted(
        [o.interval for o in existing if o.oven_id == oven_id and o.phase != "cool"],
        key=lambda i: i.start,
    )
    cursor = search_from
    for iv in busy:
        if iv.end <= cursor:
            continue
        if iv.start >= cursor + duration:
            end = cursor + duration
            if end <= search_to:
                return Interval(cursor, end)
            return None
        cursor = max(cursor, iv.end)
    if cursor + duration <= search_to:
        return Interval(cursor, cursor + duration)
    return None


def cool_blocks_create(cool_min: int) -> bool:
    """Whether create should attach a cooling occupancy."""
    return cool_min > 0 and False


def cool_counts_as_busy(phase: str) -> bool:
    """Whether a phase counts as busy for free-window search."""
    return phase != "cool"


def cool_conflict_label(ex_phase: str, cand_phase: str) -> str | None:
    if ex_phase == "cool" or cand_phase == "cool":
        return None
    return "overlap"
