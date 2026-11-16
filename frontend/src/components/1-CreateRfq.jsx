import React, { useState } from "react";
import { api } from "../api.js";
import { TRIGGER_LABEL } from "../format.js";

const pad = (n) => String(n).padStart(2, "0");
// value for <input type="datetime-local"> in local time, offset by `min` minutes from now
const local = (min) => {
  const d = new Date(Date.now() + min * 60000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const today = (days = 7) => {
  const d = new Date(Date.now() + days * 86400000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

export default function CreateRfq() {
  const [f, setF] = useState({
    name: "",
    reference_id: "",
    bid_start: local(0),
    bid_close: local(30),
    forced_close: local(60),
    pickup_date: today(),
    trigger_window_min: 10,
    extension_min: 5,
    trigger_type: "BID_RECEIVED",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    // client-side mirror of the server validation rules
    const start = new Date(f.bid_start), close = new Date(f.bid_close), forced = new Date(f.forced_close);
    if (close <= start) return setError("Bid close time must be later than bid start time");
    if (forced <= close) return setError("Forced bid close time must be later than bid close time");

    setBusy(true);
    try {
      const rfq = await api.createRfq({
        ...f,
        reference_id: f.reference_id.trim() || null,
        bid_start: start.toISOString(),
        bid_close: close.toISOString(),
        forced_close: forced.toISOString(),
        trigger_window_min: Number(f.trigger_window_min),
        extension_min: Number(f.extension_min),
      });
      window.location.hash = `#/rfq/${rfq.id}`;
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <>
      <h1>Create RFQ</h1>
      <form className="card form" onSubmit={submit}>
        {error && <div className="alert error">{error}</div>}

        <h2>RFQ details</h2>
        <div className="grid">
          <label>RFQ name
            <input required value={f.name} onChange={set("name")} placeholder="Mumbai → Rotterdam, 40ft FCL" />
          </label>
          <label>Reference ID <span className="muted small">(optional, auto-generated)</span>
            <input value={f.reference_id} onChange={set("reference_id")} placeholder="RFQ-2026-001" />
          </label>
          <label>Bid start
            <input type="datetime-local" required value={f.bid_start} onChange={set("bid_start")} />
          </label>
          <label>Bid close
            <input type="datetime-local" required value={f.bid_close} onChange={set("bid_close")} />
          </label>
          <label>Forced bid close <span className="muted small">(must be after bid close)</span>
            <input type="datetime-local" required value={f.forced_close} onChange={set("forced_close")} />
          </label>
          <label>Pickup / service date
            <input type="date" required value={f.pickup_date} onChange={set("pickup_date")} />
          </label>
        </div>

        <h2>British auction configuration</h2>
        <div className="grid">
          <label>Trigger window X (minutes)
            <input type="number" min="1" required value={f.trigger_window_min} onChange={set("trigger_window_min")} />
          </label>
          <label>Extension duration Y (minutes)
            <input type="number" min="1" required value={f.extension_min} onChange={set("extension_min")} />
          </label>
          <label className="span2">Extension trigger
            <select value={f.trigger_type} onChange={set("trigger_type")}>
              {Object.entries(TRIGGER_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="actions">
          <a href="#/" className="btn">Cancel</a>
          <button className="btn primary" disabled={busy}>{busy ? "Creating…" : "Create RFQ"}</button>
        </div>
      </form>
    </>
  );
}
