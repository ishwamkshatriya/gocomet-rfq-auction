const BASE = import.meta.env.VITE_API_URL || "/api";

async function request(path, options) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(formatError(body) || `Request failed (${res.status})`);
  }
  return body;
}

function formatError(body) {
  if (!body || !body.detail) return null;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((d) => (d.msg || "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join("; ");
  }
  return null;
}

export const api = {
  listRfqs: () => request("/rfqs"),
  getRfq: (id) => request(`/rfqs/${id}`),
  createRfq: (data) => request("/rfqs", { method: "POST", body: JSON.stringify(data) }),
  placeBid: (id, data) =>
    request(`/rfqs/${id}/bids`, { method: "POST", body: JSON.stringify(data) }),
};
