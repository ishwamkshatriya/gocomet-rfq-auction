export const fmtDateTime = (iso) =>
  new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

export const fmtMoney = (n) =>
  n == null ? "—" : Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const STATUS_LABEL = {
  UPCOMING: "Upcoming",
  ACTIVE: "Active",
  CLOSED: "Closed",
  FORCE_CLOSED: "Force Closed",
};

export const TRIGGER_LABEL = {
  BID_RECEIVED: "Bid received in last X minutes",
  ANY_RANK_CHANGE: "Any supplier rank change in last X minutes",
  L1_CHANGE: "Lowest bidder (L1) change in last X minutes",
};

export function countdown(ms) {
  if (ms <= 0) return "00:00:00";
  const s = Math.floor(ms / 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}
