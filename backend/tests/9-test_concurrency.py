"""Regression: overlapping SQLite bids must read the latest committed state."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import threading

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import services
from app.database import Base, get_db
from app.main import app


@pytest.mark.parametrize("same_supplier", [False, True])
def test_overlapping_bids_keep_both_extensions(tmp_path, monkeypatch, same_supplier):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def db_override():
        with sessions() as session:
            yield session

    now = datetime(2026, 11, 16, 12, 0)
    monkeypatch.setattr(services, "utcnow", lambda: now)
    app.dependency_overrides[get_db] = db_override
    iso = lambda value: value.isoformat() + "Z"
    first_insert = threading.Event()
    release_first = threading.Event()
    second_select = threading.Event()
    insert_count = 0
    guard = threading.Lock()

    def pause_first_insert(conn, cursor, statement, parameters, context, executemany):
        nonlocal insert_count
        if statement.startswith("SELECT rfqs") and first_insert.is_set():
            second_select.set()
        if statement.startswith("INSERT INTO bids"):
            with guard:
                insert_count += 1
                first = insert_count == 1
            if first:
                first_insert.set()
                assert release_first.wait(5)

    try:
        with TestClient(app) as client:
            created = client.post("/api/rfqs", json={
                "name": "Concurrent auction",
                "bid_start": iso(now - timedelta(minutes=5)),
                "bid_close": iso(now + timedelta(minutes=5)),
                "forced_close": iso(now + timedelta(minutes=30)),
                "pickup_date": "2026-12-01",
                "trigger_window_min": 30,
                "extension_min": 5,
                "trigger_type": "BID_RECEIVED",
            })
            assert created.status_code == 201
            rfq_id = created.json()["id"]
            event.listen(engine, "before_cursor_execute", pause_first_insert)

            def bid(carrier, amount):
                return client.post(f"/api/rfqs/{rfq_id}/bids", json={
                    "carrier_name": carrier, "freight_charges": amount,
                    "origin_charges": 0, "destination_charges": 0,
                    "transit_days": 5, "validity_days": 30,
                })

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(bid, "A", 1000)
                assert first_insert.wait(5)
                second = pool.submit(bid, "A" if same_supplier else "B", 1100 if same_supplier else 900)
                # Broken code reaches its stale SELECT here; fixed code waits
                # at BEGIN IMMEDIATE until the first transaction commits.
                second_select.wait(0.3)
                release_first.set()
                responses = [first.result(timeout=10), second.result(timeout=10)]
            assert [r.status_code for r in responses] == ([201, 400] if same_supplier else [201, 201])
            detail = client.get(f"/api/rfqs/{rfq_id}").json()
            assert len(detail["bids"]) == (1 if same_supplier else 2)
            assert detail["bid_close"] == iso(now + timedelta(minutes=10 if same_supplier else 15))
            extensions = [x for x in detail["logs"] if x["event_type"] == "EXTENSION"]
            assert len(extensions) == (1 if same_supplier else 2)
            assert any("12:05:00 -> 12:10:00" in x["message"] for x in extensions)
            if not same_supplier:
                assert any("12:10:00 -> 12:15:00" in x["message"] for x in extensions)
    finally:
        release_first.set()
        app.dependency_overrides.pop(get_db, None)
        event.remove(engine, "before_cursor_execute", pause_first_insert)
        engine.dispose()
