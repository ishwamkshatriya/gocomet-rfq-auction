import math
from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

TriggerType = Literal["BID_RECEIVED", "ANY_RANK_CHANGE", "L1_CHANGE"]


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# Stored as naive UTC; always serialised with a trailing Z so browsers parse it as UTC.
UtcDatetime = Annotated[datetime, PlainSerializer(lambda d: d.isoformat() + "Z", return_type=str)]


class RfqCreate(BaseModel):
    reference_id: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    bid_start: datetime
    bid_close: datetime
    forced_close: datetime
    pickup_date: date
    trigger_window_min: int = Field(gt=0, le=1440, description="X minutes")
    extension_min: int = Field(gt=0, le=1440, description="Y minutes")
    trigger_type: TriggerType

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("RFQ name must not be blank")
        return value

    @field_validator("bid_start", "bid_close", "forced_close")
    @classmethod
    def normalise_tz(cls, v: datetime) -> datetime:
        return _to_naive_utc(v)

    @model_validator(mode="after")
    def check_times(self):
        if self.bid_close <= self.bid_start:
            raise ValueError("Bid close time must be later than bid start time")
        if self.forced_close <= self.bid_close:
            raise ValueError("Forced bid close time must be later than bid close time")
        return self


class BidCreate(BaseModel):
    carrier_name: str = Field(min_length=1, max_length=200)
    freight_charges: float = Field(ge=0, allow_inf_nan=False)
    origin_charges: float = Field(ge=0, allow_inf_nan=False)
    destination_charges: float = Field(ge=0, allow_inf_nan=False)
    transit_days: int = Field(gt=0, le=365)
    validity_days: int = Field(gt=0, le=365)

    @field_validator("carrier_name")
    @classmethod
    def nonblank_carrier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Carrier name must not be blank")
        return value

    @model_validator(mode="after")
    def check_total(self):
        total = self.freight_charges + self.origin_charges + self.destination_charges
        if not math.isfinite(total):
            raise ValueError("Total quote must be finite")
        if total <= 0:
            raise ValueError("Total quote must be greater than zero")
        return self


class BidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    carrier_name: str
    freight_charges: float
    origin_charges: float
    destination_charges: float
    total: float
    transit_days: int
    validity_days: int
    created_at: UtcDatetime
    rank: Optional[str] = None  # "L1", "L2"... only for a supplier's current (best) bid


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    message: str
    created_at: UtcDatetime


class RfqListItem(BaseModel):
    id: int
    reference_id: str
    name: str
    lowest_bid: Optional[float]
    bid_count: int
    bid_close: UtcDatetime
    forced_close: UtcDatetime
    status: str


class RfqDetail(BaseModel):
    id: int
    reference_id: str
    name: str
    status: str
    bid_start: UtcDatetime
    original_bid_close: UtcDatetime
    bid_close: UtcDatetime
    forced_close: UtcDatetime
    pickup_date: date
    trigger_window_min: int
    extension_min: int
    trigger_type: str
    server_time: UtcDatetime
    bids: list[BidOut]
    logs: list[LogOut]
