-- British Auction RFQ: schema (PostgreSQL flavour; the app uses SQLAlchemy and runs on SQLite by default)
-- All timestamps are UTC.

CREATE TABLE rfqs (
    id                  SERIAL PRIMARY KEY,
    reference_id        VARCHAR(64)  NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    bid_start           TIMESTAMP    NOT NULL,
    original_bid_close  TIMESTAMP    NOT NULL,           -- close time as first configured
    bid_close           TIMESTAMP    NOT NULL,           -- current close time (moves on extension)
    forced_close        TIMESTAMP    NOT NULL,           -- hard limit
    pickup_date         DATE         NOT NULL,
    trigger_window_min  INTEGER      NOT NULL CHECK (trigger_window_min > 0),   -- X
    extension_min       INTEGER      NOT NULL CHECK (extension_min > 0),        -- Y
    trigger_type        VARCHAR(32)  NOT NULL
                        CHECK (trigger_type IN ('BID_RECEIVED','ANY_RANK_CHANGE','L1_CHANGE')),
    created_at          TIMESTAMP    NOT NULL,
    CHECK (bid_close > bid_start),
    CHECK (forced_close > original_bid_close),
    CHECK (bid_close <= forced_close)                    -- extensions never pass the forced close
);

CREATE TABLE bids (
    id                   SERIAL PRIMARY KEY,
    rfq_id               INTEGER NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    carrier_name         VARCHAR(200) NOT NULL,
    carrier_key          VARCHAR(200) NOT NULL,          -- lower(trim(carrier_name)): supplier identity
    freight_charges      DOUBLE PRECISION NOT NULL CHECK (freight_charges >= 0),
    origin_charges       DOUBLE PRECISION NOT NULL CHECK (origin_charges >= 0),
    destination_charges  DOUBLE PRECISION NOT NULL CHECK (destination_charges >= 0),
    total                DOUBLE PRECISION NOT NULL,      -- freight + origin + destination
    transit_days         INTEGER NOT NULL CHECK (transit_days > 0),
    validity_days        INTEGER NOT NULL CHECK (validity_days > 0),
    created_at           TIMESTAMP NOT NULL
);
CREATE INDEX ix_bids_rfq_id      ON bids (rfq_id);
CREATE INDEX ix_bids_rfq_carrier ON bids (rfq_id, carrier_key);

CREATE TABLE activity_logs (
    id          SERIAL PRIMARY KEY,
    rfq_id      INTEGER NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    event_type  VARCHAR(32) NOT NULL,   -- RFQ_CREATED | BID | EXTENSION | EXTENSION_CAPPED
    message     TEXT NOT NULL,          -- includes the reason for each extension
    created_at  TIMESTAMP NOT NULL
);
CREATE INDEX ix_activity_logs_rfq_id ON activity_logs (rfq_id);

-- Derived, not stored:
--   status   = UPCOMING (now < bid_start) | ACTIVE (now < bid_close)
--              | FORCE_CLOSED (closed and bid_close = forced_close) | CLOSED
--   ranking  = each supplier's lowest bid, ordered by (total, created_at) -> L1, L2, ...
