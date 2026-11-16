from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models, services
from .database import Base, engine, get_db
from .schemas import BidCreate, BidOut, LogOut, RfqCreate, RfqDetail, RfqListItem


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="British Auction RFQ", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc: RequestValidationError):
    # Do not echo non-finite input values: they are not valid JSON and can
    # otherwise turn a validation error into a server serialization failure.
    details = [
        {"type": error["type"], "loc": error["loc"], "msg": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


def _get_rfq(db: Session, rfq_id: int, lock: bool = False) -> models.Rfq:
    if lock and db.get_bind().dialect.name == "sqlite":
        # SQLite ignores SELECT FOR UPDATE. Reserve its write lock before
        # reading auction state so overlapping bids cannot lose extensions
        # or validate against a stale supplier best bid.
        db.execute(text("BEGIN IMMEDIATE"))
    q = db.query(models.Rfq).filter(models.Rfq.id == rfq_id)
    if lock:
        q = q.with_for_update()  # row-level lock on PostgreSQL
    rfq = q.first()
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    return rfq


def _detail(rfq: models.Rfq) -> RfqDetail:
    now = services.utcnow()
    labels = services.rank_labels(rfq.bids)
    bids = []
    for b in sorted(rfq.bids, key=lambda b: (b.total, b.created_at, b.id)):
        out = BidOut.model_validate(b)
        out.rank = labels.get(b.id)
        bids.append(out)
    return RfqDetail(
        id=rfq.id,
        reference_id=rfq.reference_id,
        name=rfq.name,
        status=services.compute_status(rfq, now),
        bid_start=rfq.bid_start,
        original_bid_close=rfq.original_bid_close,
        bid_close=rfq.bid_close,
        forced_close=rfq.forced_close,
        pickup_date=rfq.pickup_date,
        trigger_window_min=rfq.trigger_window_min,
        extension_min=rfq.extension_min,
        trigger_type=rfq.trigger_type,
        server_time=now,
        bids=bids,
        logs=[LogOut.model_validate(l) for l in sorted(rfq.logs, key=lambda l: l.id, reverse=True)],
    )


@app.post("/api/rfqs", response_model=RfqDetail, status_code=201)
def create_rfq(payload: RfqCreate, db: Session = Depends(get_db)):
    try:
        rfq = services.create_rfq(db, payload)
    except services.AuctionError as e:
        raise HTTPException(409, str(e))
    return _detail(rfq)


@app.get("/api/rfqs", response_model=list[RfqListItem])
def list_rfqs(db: Session = Depends(get_db)):
    now = services.utcnow()
    items = []
    for rfq in db.query(models.Rfq).order_by(models.Rfq.id.desc()).all():
        lowest = min((b.total for b in rfq.bids), default=None)
        items.append(
            RfqListItem(
                id=rfq.id,
                reference_id=rfq.reference_id,
                name=rfq.name,
                lowest_bid=lowest,
                bid_count=len(rfq.bids),
                bid_close=rfq.bid_close,
                forced_close=rfq.forced_close,
                status=services.compute_status(rfq, now),
            )
        )
    return items


@app.get("/api/rfqs/{rfq_id}", response_model=RfqDetail)
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    return _detail(_get_rfq(db, rfq_id))


@app.post("/api/rfqs/{rfq_id}/bids", response_model=RfqDetail, status_code=201)
def submit_bid(rfq_id: int, payload: BidCreate, db: Session = Depends(get_db)):
    rfq = _get_rfq(db, rfq_id, lock=True)
    try:
        services.place_bid(db, rfq, payload)
    except services.AuctionError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _detail(rfq)
