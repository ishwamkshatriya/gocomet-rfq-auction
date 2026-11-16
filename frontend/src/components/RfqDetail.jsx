import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { countdown, fmtDateTime, fmtMoney, TRIGGER_LABEL } from "../format.js";
import StatusBadge from "./StatusBadge.jsx";

const EMPTY_BID = {
  carrier_name: "",
  freight_charges: "",
  origin_charges: "",
  destination_charges: "",
  transit_days: "",
  validity_days: "",
};

export default function RfqDetail({ id }) {
  const [rfq, setRfq] = useState(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const offset = useRef(0); // serverTime - clientTime

  const load = useCallback(async () => {
    try {
      const d = await api.getRfq(id);
      offset.current = new Date(d.server_time).getTime() - Date.now();
      setRfq(d);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    load();
    const poll = setInterval(load, 3000);
    const tick = setInterval(() => setNow(Date.now()), 500);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [load]);

  if (error && !rfq) return <div className="alert error">{error}</div>;
  if (!rfq) return <p className="muted">Loading…</p>;

  const serverNow = now + offset.current;
  const remaining = new Date(rfq.bid_close).getTime() - serverNow;
  const started = serverNow >= new Date(rfq.bid_start).getTime();
  const open = started && remaining > 0;
  const extended = new Date(rfq.bid_close) > new Date(rfq.original_bid_close);
  const lowest = rfq.bids.length ? rfq.bids[0].total : null;
  const inWindow = open && remaining <= rfq.trigger_window_min * 60000;

  return (
    <>
      <div className="page-head">
        <div>
          <a href="#/" className="muted small">← All auctions</a>
          <h1>{rfq.name}</h1>
          <div className="muted">{rfq.reference_id} · Pickup {rfq.pickup_date}</div>
        </div>
        <StatusBadge status={rfq.status} />
      </div>

      <section className="stats">
        <div className="card stat">
          <div className="label">{open ? "Time remaining" : started ? "Auction ended" : "Starts"}</div>
          <div className={`value mono ${inWindow ? "hot" : ""}`}>
            {open ? countdown(remaining) : started ? "00:00:00" : fmtDateTime(rfq.bid_start)}
          </div>
          {inWindow && <div className="small hot">In trigger window</div>}
        </div>
        <div className="card stat">
          <div className="label">Current lowest bid (L1)</div>
          <div className="value">{fmtMoney(lowest)}</div>
          <div className="muted small">{rfq.bids.filter((b) => b.rank).length} suppliers</div>
        </div>
        <div className="card stat">
          <div className="label">Bid close {extended && <span className="pill">extended</span>}</div>
          <div className="value small-val">{fmtDateTime(rfq.bid_close)}</div>
          {extended && <div className="muted small">Original {fmtDateTime(rfq.original_bid_close)}</div>}
        </div>
        <div className="card stat">
          <div className="label">Forced close</div>
          <div className="value small-val">{fmtDateTime(rfq.forced_close)}</div>
          <div className="muted small">Hard limit</div>
        </div>
      </section>

      <div className="two-col">
        <div>
          <section className="card">
            <h2>Supplier bids</h2>
            {rfq.bids.length === 0 ? (
              <p className="muted">No bids yet.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Carrier</th>
                      <th className="num">Freight</th>
                      <th className="num">Origin</th>
                      <th className="num">Dest.</th>
                      <th className="num">Total</th>
                      <th>Transit</th>
                      <th>Valid</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rfq.bids.map((b) => (
                      <tr key={b.id} className={b.rank ? "" : "superseded"}>
                        <td>{b.rank ? <span className={`rank ${b.rank === "L1" ? "l1" : ""}`}>{b.rank}</span> : <span className="muted">—</span>}</td>
                        <td>{b.carrier_name}</td>
                        <td className="num">{fmtMoney(b.freight_charges)}</td>
                        <td className="num">{fmtMoney(b.origin_charges)}</td>
                        <td className="num">{fmtMoney(b.destination_charges)}</td>
                        <td className="num strong">{fmtMoney(b.total)}</td>
                        <td>{b.transit_days}d</td>
                        <td>{b.validity_days}d</td>
                        <td className="small">{fmtDateTime(b.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted small">Bids sorted by price. Greyed rows are superseded by the same supplier's lower bid.</p>
          </section>

          <section className="card">
            <h2>Activity log</h2>
            <ul className="log">
              {rfq.logs.map((l) => (
                <li key={l.id} className={l.event_type.toLowerCase()}>
                  <span className="mono small muted">{fmtDateTime(l.created_at)}</span>
                  <span className="tag">{l.event_type.replace("_", " ")}</span>
                  <span>{l.message}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div>
          <section className="card">
            <h2>Auction configuration</h2>
            <dl className="config">
              <dt>Trigger window (X)</dt><dd>{rfq.trigger_window_min} min</dd>
              <dt>Extension (Y)</dt><dd>{rfq.extension_min} min</dd>
              <dt>Trigger</dt><dd>{TRIGGER_LABEL[rfq.trigger_type]}</dd>
              <dt>Bid start</dt><dd>{fmtDateTime(rfq.bid_start)}</dd>
            </dl>
          </section>

          <BidForm rfq={rfq} open={open} onPlaced={setRfq} />
        </div>
      </div>
    </>
  );
}

function BidForm({ rfq, open, onPlaced }) {
  const [f, setF] = useState(EMPTY_BID);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const total = ["freight_charges", "origin_charges", "destination_charges"].reduce(
    (s, k) => s + (Number(f[k]) || 0),
    0
  );

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const updated = await api.placeBid(rfq.id, {
        carrier_name: f.carrier_name,
        freight_charges: Number(f.freight_charges),
        origin_charges: Number(f.origin_charges),
        destination_charges: Number(f.destination_charges),
        transit_days: Number(f.transit_days),
        validity_days: Number(f.validity_days),
      });
      onPlaced(updated);
      setF((p) => ({ ...EMPTY_BID, carrier_name: p.carrier_name, transit_days: p.transit_days, validity_days: p.validity_days }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2>Submit a quote</h2>
      {!open && <div className="alert">Bidding is not open for this auction.</div>}
      <form className="form" onSubmit={submit}>
        {error && <div className="alert error">{error}</div>}
        <label>Carrier name
          <input required disabled={!open} value={f.carrier_name} onChange={set("carrier_name")} />
        </label>
        <label>Freight charges
          <input type="number" min="0" step="0.01" required disabled={!open} value={f.freight_charges} onChange={set("freight_charges")} />
        </label>
        <label>Origin charges
          <input type="number" min="0" step="0.01" required disabled={!open} value={f.origin_charges} onChange={set("origin_charges")} />
        </label>
        <label>Destination charges
          <input type="number" min="0" step="0.01" required disabled={!open} value={f.destination_charges} onChange={set("destination_charges")} />
        </label>
        <div className="grid">
          <label>Transit time (days)
            <input type="number" min="1" required disabled={!open} value={f.transit_days} onChange={set("transit_days")} />
          </label>
          <label>Quote validity (days)
            <input type="number" min="1" required disabled={!open} value={f.validity_days} onChange={set("validity_days")} />
          </label>
        </div>
        <div className="total-row">Total <strong>{fmtMoney(total)}</strong></div>
        <button className="btn primary" disabled={!open || busy}>{busy ? "Submitting…" : "Submit bid"}</button>
        <p className="muted small">A supplier's new bid must be lower than its own previous bid.</p>
      </form>
    </section>
  );
}
