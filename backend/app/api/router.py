from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Batch, ConflictLog, Oven, Product
from app.schemas.schemas import (
    BatchCreate,
    BatchOut,
    ConflictOut,
    GanttBlock,
    OvenOut,
    OvenUpdate,
    ProductOut,
    WindowOut,
)
from app.services.oven_engine import (
    Occupancy,
    PHASE_LABELS,
    RecipeDurations,
    build_occupancies,
    find_conflicts,
    next_free_window,
)

api_router = APIRouter()


def _recipe(p: Product) -> RecipeDurations:
    return RecipeDurations(p.ferment_min, p.bake_min)


def _fmt_min(m: int) -> str:
    m = max(m, 0)
    return f"{m // 60:02d}:{m % 60:02d}"


def _all_occupancies(db: Session) -> list[Occupancy]:
    """All busy intervals, including each batch's oven cooling tail."""
    batches = db.scalars(select(Batch)).all()
    out: list[Occupancy] = []
    for b in batches:
        p = db.get(Product, b.product_id)
        o = db.get(Oven, b.oven_id)
        if not p:
            continue
        cool_min = o.cool_min if o else 0
        out.extend(build_occupancies(b.oven_id, b.id, b.start_min, _recipe(p), cool_min))
    return out


def _batch_out(db: Session, b: Batch) -> BatchOut:
    p = db.get(Product, b.product_id)
    o = db.get(Oven, b.oven_id)
    ferment_end = b.start_min + (p.ferment_min if p else 0)
    bake_end = ferment_end + (p.bake_min if p else 0)
    cool_end = bake_end + (o.cool_min if o else 0)
    return BatchOut(
        id=b.id,
        product_id=b.product_id,
        oven_id=b.oven_id,
        code=b.code,
        start_min=b.start_min,
        status=b.status,
        product_name=p.name if p else None,
        oven_label=o.label if o else None,
        ferment_end=ferment_end,
        bake_end=bake_end,
        cool_end=cool_end,
    )


def _conflict_detail(ex: Occupancy, cand: Occupancy, code: str) -> str:
    """Human-readable rejection; cooling clashes must say so with cool start/end."""
    if ex.phase == "cool" and cand.phase == "cool":
        # both tails overlap; the new batch (id -1 at create time) is named
        cool, other = cand, ex
        cool_who, other_who = f"新批次 {code}", f"批次#{other.batch_id}"
    elif ex.phase == "cool":
        # an earlier batch's cooling tail blocks the new batch's ferment/bake
        cool, other = ex, cand
        cool_who = f"批次#{cool.batch_id}"
        other_who = f"新批次 {code}"
    elif cand.phase == "cool":
        # the new batch's cooling tail runs into an already scheduled batch
        cool, other = cand, ex
        cool_who = f"新批次 {code}"
        other_who = f"批次#{other.batch_id}"
    else:
        return (
            f"与批次#{ex.batch_id} 的{PHASE_LABELS[ex.phase]}段重叠："
            f"[{cand.interval.start},{cand.interval.end})"
        )
    # 冷却与下一批的发酵/烘烤重叠：写出冷却起止（半开区间）
    return (
        f"冷却冲突：{cool_who} 冷却段 {_fmt_min(cool.interval.start)}"
        f"–{_fmt_min(cool.interval.end)}（[{cool.interval.start},{cool.interval.end})）"
        f"与{other_who}{PHASE_LABELS[other.phase]}段 "
        f"[{other.interval.start},{other.interval.end}) 重叠"
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.id)).all()


@api_router.get("/ovens", response_model=list[OvenOut])
def ovens(db: Session = Depends(get_db)):
    return db.scalars(select(Oven).order_by(Oven.id)).all()


@api_router.patch("/ovens/{oven_id}", response_model=OvenOut)
def update_oven(oven_id: int, body: OvenUpdate, db: Session = Depends(get_db)):
    oven = db.get(Oven, oven_id)
    if not oven:
        raise HTTPException(404, "炉位不存在")
    oven.cool_min = body.cool_min
    db.commit()
    db.refresh(oven)
    return oven


@api_router.get("/batches", response_model=list[BatchOut])
def batches(db: Session = Depends(get_db)):
    rows = db.scalars(select(Batch).order_by(Batch.start_min)).all()
    return [_batch_out(db, b) for b in rows]


@api_router.post("/batches", response_model=BatchOut)
def create_batch(body: BatchCreate, db: Session = Depends(get_db)):
    product = db.get(Product, body.product_id)
    oven = db.get(Oven, body.oven_id)
    if not product or not oven:
        raise HTTPException(404, "产品或炉位不存在")
    recipe = _recipe(product)
    candidates = build_occupancies(oven.id, -1, body.start_min, recipe, oven.cool_min)
    existing = _all_occupancies(db)
    hits = find_conflicts(existing, candidates)
    code = body.code or f"BO-{body.start_min}"
    if hits:
        detail = _conflict_detail(*hits[0], code=code)
        db.add(ConflictLog(batch_code=code, oven_id=oven.id, detail=detail))
        db.commit()
        raise HTTPException(409, detail)
    batch = Batch(
        product_id=product.id,
        oven_id=oven.id,
        code=code,
        start_min=body.start_min,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_out(db, batch)


@api_router.get("/gantt", response_model=list[GanttBlock])
def gantt(db: Session = Depends(get_db)):
    blocks: list[GanttBlock] = []
    for b in db.scalars(select(Batch).order_by(Batch.start_min)).all():
        p = db.get(Product, b.product_id)
        o = db.get(Oven, b.oven_id)
        if not p or not o:
            continue
        for occ in build_occupancies(b.oven_id, b.id, b.start_min, _recipe(p), o.cool_min):
            blocks.append(
                GanttBlock(
                    batch_id=b.id,
                    code=b.code,
                    oven_id=o.id,
                    oven_label=o.label,
                    phase=occ.phase,
                    start_min=occ.interval.start,
                    end_min=occ.interval.end,
                )
            )
    return blocks


@api_router.get("/conflicts", response_model=list[ConflictOut])
def conflicts(db: Session = Depends(get_db)):
    return db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).all()


@api_router.get("/windows", response_model=list[WindowOut])
def windows(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "产品不存在")
    duration = product.ferment_min + product.bake_min
    # Cooling tails ride along in existing occupancies, so they count as busy
    # and are never recommended as a free gap.
    existing = _all_occupancies(db)
    out: list[WindowOut] = []
    for oven in db.scalars(select(Oven).order_by(Oven.id)).all():
        w = next_free_window(existing, oven.id, duration, search_from=8 * 60, search_to=22 * 60)
        if w:
            out.append(
                WindowOut(
                    oven_id=oven.id,
                    oven_label=oven.label,
                    start_min=w.start,
                    end_min=w.end,
                    duration_min=duration,
                )
            )
    return out
