// shortcut: in-memory fixed window per function instance (Edge instances are short-lived and not
// shared), so a determined caller can exceed it across instances; upgrade to a database counter if abused.
const WINDOW_MS = 60_000;
export const MAX_PER_WINDOW = 30;
const hits = new Map<string, { start: number; count: number }>();

/** True while `key` (a user id) is under MAX_PER_WINDOW requests in the current minute. */
export function allowRequest(key: string, now = Date.now()): boolean {
  const entry = hits.get(key);
  if (!entry || now - entry.start >= WINDOW_MS) {
    // Drop expired entries so the map cannot grow without bound.
    if (hits.size > 1000) {
      for (const [k, v] of hits) if (now - v.start >= WINDOW_MS) hits.delete(k);
    }
    hits.set(key, { start: now, count: 1 });
    return true;
  }
  entry.count++;
  return entry.count <= MAX_PER_WINDOW;
}
