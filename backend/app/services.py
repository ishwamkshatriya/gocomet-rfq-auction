"""Auction engine: ranking, status and the British Auction extension logic."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .models import ANY_RANK_CHANGE, BID_RECEIVED, L1_CHANGE
from .schemas import BidCreate, RfqCreate


class AuctionError(Exception):
    """Business-rule violation (mapped to HTTP 400/409 by the API layer)."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


# ---------------------------------------------------------------- status / ranking

def compute_status(rfq: models.Rfq, now: Optional[datetime] = None) -> str:
    now = now or utcnow()
    if now < rfq.bid_start:
        return "UPCOMING"
    if now < rfq.bid_close:
        return "ACTIVE"
    # Closed. If the close time was pushed all the way to the forced close it is a Force Close.
    return "FORCE_CLOSED" if rfq.bid_close >= rfq.forced_close else "CLOSED"


def current_ranking(bids: list[models.Bid]) -> list[models.Bid]:
    """Each supplier's best (lowest) bid, ordered L1, L2, ... Ties go to the earlier bid."""
    best: dict[str, models.Bid] = {}
    for b in bids:
        cur = best.get(b.carrier_key)
        if cur is None or (b.total, b.created_at, b.id or 0) < (cur.total, cur.created_at, cur.id or 0):
            best[b.carrier_key] = b
    return sorted(best.values(), key=lambda b: (b.total, b.created_at, b.id or 0))


def rank_labels(bids: list[models.Bid]) -> dict[int, str]:
    return {b.id: f"L{i}" for i, b in enumerate(current_ranking(bids), start=1)}


# ---------------------------------------------------------------- RFQ creation

def create_rfq(db: Session, data: RfqCreate, now: Optional[datetime] = None) -> models.Rfq:
    now = now or utcnow()
    reference_id = (data.reference_id or "").strip() or f"RFQ-{uuid.uuid4().hex[:8].upper()}"
    if db.query(models.Rfq).filter_by(reference_id=reference_id).first():
        raise AuctionError(f"Reference ID '{reference_id}' already exists")

    rfq = models.Rfq(
        reference_id=reference_id,
        name=data.name.strip(),
        bid_start=data.bid_start,
        original_bid_close=data.bid_close,
        bid_close=data.bid_close,
        forced_close=data.forced_close,
        pickup_date=data.pickup_date,
        trigger_window_min=data.trigger_window_min,
        extension_min=data.extension_min,
        trigger_type=data.trigger_type,
        created_at=now,
    )
    rfq.logs.append(
        models.ActivityLog(
            event_type="RFQ_CREATED",
            message=f"RFQ created. Close {fmt(data.bid_close)} UTC, forced close {fmt(data.forced_close)} UTC.",
            created_at=now,
        )
    )
    db.add(rfq)
    db.commit()
    return rfq


# ---------------------------------------------------------------- bidding

def _trigger_reason(rfq, prev_rank: list[str], new_rank: list[str], carrier_key: str) -> Optional[str]:
    """Return a human reason if this bid satisfies the RFQ's trigger condition."""
    if rfq.trigger_type == BID_RECEIVED:
        return "a bid was received in the trigger window"
    if rfq.trigger_type == ANY_RANK_CHANGE:
        if prev_rank != new_rank:
            return "supplier ranking changed in the trigger window"
        return None
    if rfq.trigger_type == L1_CHANGE:
        prev_l1 = prev_rank[0] if prev_rank else None
        if new_rank and new_rank[0] != prev_l1:
            return "the lowest bidder (L1) changed in the trigger window"
        return None
    return None


def place_bid(db: Session, rfq: models.Rfq, data: BidCreate, now: Optional[datetime] = None) -> models.Bid:
    now = now or utcnow()
    if now < rfq.bid_start:
        raise AuctionError("Bidding has not started yet")
    if now >= rfq.bid_close:
        raise AuctionError("Auction is closed; bids are no longer accepted")

    carrier = data.carrier_name.strip()
    key = carrier.lower()
    total = round(data.freight_charges + data.origin_charges + data.destination_charges, 2)

    prev_ranking = current_ranking(rfq.bids)
    prev_rank = [b.carrier_key for b in prev_ranking]
    own_best = next((b.total for b in prev_ranking if b.carrier_key == key), None)
    if own_best is not None and total >= own_best:
        raise AuctionError(
            f"New bid ({total:.2f}) must be lower than your current best bid ({own_best:.2f})"
        )

    bid = models.Bid(
        carrier_name=carrier,
        carrier_key=key,
        freight_charges=data.freight_charges,
        origin_charges=data.origin_charges,
        destination_charges=data.destination_charges,
        total=total,
        transit_days=data.transit_days,
        validity_days=data.validity_days,
        created_at=now,
    )
    rfq.bids.append(bid)
    db.flush()

    new_rank = [b.carrier_key for b in current_ranking(rfq.bids)]
    new_pos = new_rank.index(key) + 1
    rfq.logs.append(
        models.ActivityLog(
            event_type="BID",
            message=f"{carrier} submitted a bid of {total:.2f} (now L{new_pos}).",
            created_at=now,
        )
    )

    # ---- British auction extension
    window_start = rfq.bid_close - timedelta(minutes=rfq.trigger_window_min)
    if window_start <= now < rfq.bid_close:
        reason = _trigger_reason(rfq, prev_rank, new_rank, key)
        if reason:
            _extend(rfq, now, f"{carrier}'s bid at {fmt(now)}: {reason}")

    db.commit()
    return bid


def _extend(rfq: models.Rfq, now: datetime, reason: str) -> None:
    old_close = rfq.bid_close
    proposed = old_close + timedelta(minutes=rfq.extension_min)
    new_close = min(proposed, rfq.forced_close)  # never beyond the forced close

    if new_close <= old_close:
        rfq.logs.append(
            models.ActivityLog(
                event_type="EXTENSION_CAPPED",
                message=f"Extension not applied ({reason}): auction is already at forced close {fmt(rfq.forced_close)} UTC.",
                created_at=now,
            )
        )
        return

    rfq.bid_close = new_close
    capped = " (capped at forced close)" if new_close < proposed else ""
    rfq.logs.append(
        models.ActivityLog(
            event_type="EXTENSION",
            message=(
                f"Close time extended {fmt(old_close)} -> {fmt(new_close)} UTC{capped}. "
                f"Reason: {reason}."
            ),
            created_at=now,
        )
    )
