async function req(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const msg = data?.detail || data?.error || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

export const api = {
  dashboard: () => req("/dashboard"),
  rooms: () => req("/rooms"),
  teachers: () => req("/teachers"),
  datasets: () => req("/datasets"),
  setDatasetAvailability: (code, available) =>
    req(`/datasets/${code}/availability`, {
      method: "POST",
      body: JSON.stringify({ available }),
    }),
  sessions: () => req("/sessions"),
  leases: (bypassOnly = false) => req(`/leases${bypassOnly ? "?bypass=1" : ""}`),
  conflicts: () => req("/conflicts"),
  openLease: (session_code) =>
    req("/leases/open", { method: "POST", body: JSON.stringify({ session_code }) }),
  closeLease: (lease_no) =>
    req("/leases/close", { method: "POST", body: JSON.stringify({ lease_no }) }),
};
