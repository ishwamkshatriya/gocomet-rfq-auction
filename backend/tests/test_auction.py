from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, services
from app.database import Base
from app.schemas import BidCreate, RfqCreate

T0 = datetime(2026, 1, 1, 17, 0)  # bid start
CLOSE = datetime(2026, 1, 1, 18, 0)
FORCED = datetime(2026, 1, 1, 18, 20)


def at(h, m, s=0):
    return datetime(2026, 1, 1, h, m, s)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


def make_rfq(db, trigger, x=10, y=5):
    return services.create_rfq(
        db,
        RfqCreate(
            name="Mumbai -> Rotterdam",
            bid_start=T0,
            bid_close=CLOSE,
            forced_close=FORCED,
            pickup_date=date(2026, 2, 1),
            trigger_window_min=x,
            extension_min=y,
            trigger_type=trigger,
        ),
        now=T0,
    )


def bid(db, rfq, carrier, total, now):
    return services.place_bid(
        db,
        rfq,
        BidCreate(
            carrier_name=carrier,
            freight_charges=total - 20,
            origin_charges=10,
            destination_charges=10,
            transit_days=10,
            validity_days=30,
        ),
        now=now,
    )


# ---------------- validation

def test_forced_close_must_be_after_close():
    with pytest.raises(ValidationError):
        RfqCreate(
            name="x", bid_start=T0, bid_close=CLOSE, forced_close=CLOSE,
            pickup_date=date(2026, 2, 1), trigger_window_min=5, extension_min=5,
            trigger_type="BID_RECEIVED",
        )


def test_bid_outside_window_does_not_extend(db):
    rfq = make_rfq(db, "BID_RECEIVED")
    bid(db, rfq, "A", 1000, at(17, 30))
    assert rfq.bid_close == CLOSE


def test_bid_after_close_rejected(db):
    rfq = make_rfq(db, "BID_RECEIVED")
    with pytest.raises(services.AuctionError):
        bid(db, rfq, "A", 1000, CLOSE)


def test_bid_before_start_rejected(db):
    rfq = make_rfq(db, "BID_RECEIVED")
    with pytest.raises(services.AuctionError):
        bid(db, rfq, "A", 1000, at(16, 59))


def test_supplier_must_lower_own_bid(db):
    rfq = make_rfq(db, "BID_RECEIVED")
    bid(db, rfq, "A", 1000, at(17, 10))
    with pytest.raises(services.AuctionError):
        bid(db, rfq, "a", 1000, at(17, 11))


# ---------------- triggers

def test_bid_received_extends(db):
    rfq = make_rfq(db, "BID_RECEIVED")
    bid(db, rfq, "A", 1000, at(17, 55))
    assert rfq.bid_close == at(18, 5)
    assert any(l.event_type == "EXTENSION" for l in rfq.logs)


def test_any_rank_change(db):
    rfq = make_rfq(db, "ANY_RANK_CHANGE")
    bid(db, rfq, "A", 1000, at(17, 10))
    bid(db, rfq, "B", 900, at(17, 11))      # B takes L1 (outside window)
    bid(db, rfq, "B", 890, at(17, 55))      # B still L1, order unchanged -> no extension
    assert rfq.bid_close == CLOSE
    bid(db, rfq, "A", 880, at(17, 56))      # A overtakes B -> rank change
    assert rfq.bid_close == at(18, 5)


def test_l1_change_only(db):
    rfq = make_rfq(db, "L1_CHANGE")
    bid(db, rfq, "A", 1000, at(17, 10))
    bid(db, rfq, "B", 900, at(17, 11))
    bid(db, rfq, "C", 950, at(17, 55))      # C enters as L2, L1 unchanged -> no extension
    assert rfq.bid_close == CLOSE
    bid(db, rfq, "C", 850, at(17, 57))      # C becomes L1 -> extends
    assert rfq.bid_close == at(18, 5)


def test_new_supplier_counts_as_rank_change(db):
    rfq = make_rfq(db, "ANY_RANK_CHANGE")
    bid(db, rfq, "A", 1000, at(17, 10))
    bid(db, rfq, "B", 1100, at(17, 55))     # new supplier joins as L2
    assert rfq.bid_close == at(18, 5)


# ---------------- forced close

def test_extension_capped_at_forced_close(db):
    rfq = make_rfq(db, "BID_RECEIVED", x=10, y=15)
    bid(db, rfq, "A", 1000, at(17, 55))
    assert rfq.bid_close == at(18, 15)      # 18:00 + 15 min, below the cap
    bid(db, rfq, "A", 990, at(18, 10))      # 18:15 + 15 = 18:30 -> capped at 18:20
    assert rfq.bid_close == FORCED


def test_never_exceeds_forced_and_force_closes(db):
    rfq = make_rfq(db, "BID_RECEIVED", x=10, y=5)
    price = 1000
    t = at(17, 55)
    # keep bidding one minute before each (extended) close until the forced close is reached
    for _ in range(10):
        if t >= rfq.bid_close:
            break
        price -= 10
        bid(db, rfq, "A", price, t)
        assert rfq.bid_close <= FORCED
        t = rfq.bid_close - timedelta(minutes=1)
    assert rfq.bid_close == FORCED
    # one more bid inside the last window cannot extend further
    bid(db, rfq, "A", price - 10, at(18, 19))
    assert rfq.bid_close == FORCED
    assert any(l.event_type == "EXTENSION_CAPPED" for l in rfq.logs)
    assert services.compute_status(rfq, at(18, 21)) == "FORCE_CLOSED"
    with pytest.raises(services.AuctionError):
        bid(db, rfq, "B", 500, at(18, 20))


def test_status_and_ranking(db):
    rfq = make_rfq(db, "BID_RECEIVED")
    assert services.compute_status(rfq, at(16, 0)) == "UPCOMING"
    assert services.compute_status(rfq, at(17, 30)) == "ACTIVE"
    assert services.compute_status(rfq, at(18, 1)) == "CLOSED"
    bid(db, rfq, "A", 1000, at(17, 10))
    bid(db, rfq, "B", 900, at(17, 11))
    bid(db, rfq, "A", 800, at(17, 12))
    labels = services.rank_labels(rfq.bids)
    ranked = services.current_ranking(rfq.bids)
    assert [b.carrier_name for b in ranked] == ["A", "B"]
    assert sorted(labels.values()) == ["L1", "L2"]
