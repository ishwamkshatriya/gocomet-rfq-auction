import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { fmtDateTime, fmtMoney } from "../format.js";
import StatusBadge from "./StatusBadge.jsx";

export default function RfqList() {
  const [rfqs, setRfqs] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .listRfqs()
        .then((d) => alive && (setRfqs(d), setError("")))
        .catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <>
      <h1>British Auctions</h1>
      {error && <div className="alert error">{error}</div>}
      {!rfqs && !error && <p className="muted">Loading…</p>}
      {rfqs && rfqs.length === 0 && (
        <div className="card empty">
          No auctions yet. <a href="#/new">Create your first RFQ</a>.
        </div>
      )}
      {rfqs && rfqs.length > 0 && (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>RFQ</th>
                <th className="num">Lowest bid</th>
                <th>Bid close</th>
                <th>Forced close</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rfqs.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => (window.location.hash = `#/rfq/${r.id}`)}>
                  <td>
                    <a href={`#/rfq/${r.id}`}>{r.name}</a>
                    <div className="muted small">{r.reference_id} · {r.bid_count} bids</div>
                  </td>
                  <td className="num">{fmtMoney(r.lowest_bid)}</td>
                  <td>{fmtDateTime(r.bid_close)}</td>
                  <td>{fmtDateTime(r.forced_close)}</td>
                  <td><StatusBadge status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
