from datetime import datetime
import pytest
from pydantic import ValidationError
from app.schemas import RfqCreate, BidCreate


def rfq(name):
    return RfqCreate(name=name, bid_start='2026-11-16T12:00:00Z',
        bid_close='2026-11-16T13:00:00Z', forced_close='2026-11-16T14:00:00Z',
        pickup_date='2026-12-01',trigger_window_min=5,extension_min=5,trigger_type='BID_RECEIVED')


def quote(**kwargs):
    data = dict(carrier_name='Carrier',freight_charges=100,origin_charges=10,
        destination_charges=10,transit_days=5,validity_days=30)
    data.update(kwargs)
    return BidCreate(**data)


@pytest.mark.parametrize('blank',[' ', '\t\n', '\u2003'])
def test_blank_rfq_rejected(blank):
    with pytest.raises(ValidationError):
        rfq(blank)


@pytest.mark.parametrize('blank',[' ', '\t\n', '\u2003'])
def test_blank_carrier_rejected(blank):
    with pytest.raises(ValidationError):
        quote(carrier_name=blank)


@pytest.mark.parametrize('field',['freight_charges','origin_charges','destination_charges'])
@pytest.mark.parametrize('value',[float('inf'),float('-inf'),float('nan'),'Infinity','NaN'])
def test_nonfinite_charge_rejected(field,value):
    with pytest.raises(ValidationError):
        quote(**{field:value})


def test_total_overflow_rejected():
    with pytest.raises(ValidationError):
        quote(freight_charges=1e308,origin_charges=1e308)


def test_names_trimmed_and_valid_bid_accepted():
    assert rfq('  RFQ A  ').name == 'RFQ A'
    assert quote(carrier_name='  Carrier  ').carrier_name == 'Carrier'


def test_api_nonfinite_charge_returns_422_without_persisting(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import services
    from app.database import Base, get_db
    from app.main import app
    engine = create_engine(f"sqlite:///{tmp_path / 'validation.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine,expire_on_commit=False)
    def db_override():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(services,'utcnow',lambda:datetime(2026,11,16,12,30))
    try:
        with TestClient(app,raise_server_exceptions=False) as client:
            created = client.post('/api/rfqs',json=rfq('Valid').model_dump(mode='json'))
            assert created.status_code == 201
            path = f"/api/rfqs/{created.json()['id']}"
            for amount in ['1e309','"Infinity"','"NaN"']:
                raw = '{"carrier_name":"Bad","freight_charges":'+amount+',"origin_charges":0,"destination_charges":0,"transit_days":5,"validity_days":30}'
                response = client.post(path+'/bids',content=raw,headers={'Content-Type':'application/json'})
                assert response.status_code == 422
                assert response.json()['detail']
            assert client.get(path).json()['bids'] == []
    finally:
        app.dependency_overrides.pop(get_db,None)
        engine.dispose()
