from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Extension trigger types
BID_RECEIVED = "BID_RECEIVED"
ANY_RANK_CHANGE = "ANY_RANK_CHANGE"
L1_CHANGE = "L1_CHANGE"
TRIGGER_TYPES = (BID_RECEIVED, ANY_RANK_CHANGE, L1_CHANGE)


class Rfq(Base):
    """An RFQ configured as a British Auction. All datetimes are naive UTC."""

    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    bid_start: Mapped[datetime] = mapped_column(DateTime)
    original_bid_close: Mapped[datetime] = mapped_column(DateTime)
    bid_close: Mapped[datetime] = mapped_column(DateTime)  # current, moves on extension
    forced_close: Mapped[datetime] = mapped_column(DateTime)
    pickup_date: Mapped[date] = mapped_column(Date)

    # British auction configuration
    trigger_window_min: Mapped[int] = mapped_column(Integer)  # X
    extension_min: Mapped[int] = mapped_column(Integer)  # Y
    trigger_type: Mapped[str] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(DateTime)

    bids: Mapped[list["Bid"]] = relationship(
        back_populates="rfq", order_by="Bid.id", cascade="all, delete-orphan"
    )
    logs: Mapped[list["ActivityLog"]] = relationship(
        back_populates="rfq", order_by="ActivityLog.id", cascade="all, delete-orphan"
    )


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (Index("ix_bids_rfq_carrier", "rfq_id", "carrier_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), index=True)
    carrier_name: Mapped[str] = mapped_column(String(200))
    carrier_key: Mapped[str] = mapped_column(String(200))  # lower-cased, used for identity
    freight_charges: Mapped[float] = mapped_column(Float)
    origin_charges: Mapped[float] = mapped_column(Float)
    destination_charges: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    transit_days: Mapped[int] = mapped_column(Integer)
    validity_days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    rfq: Mapped[Rfq] = relationship(back_populates="bids")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))  # RFQ_CREATED | BID | EXTENSION | EXTENSION_CAPPED
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    rfq: Mapped[Rfq] = relationship(back_populates="logs")
