import { useEffect, useState } from "react";
import { startResourceRequest, visibleResource, type Resource, type StoredResource } from "./resource";
export type { Resource } from "./resource";

// Key gating hides stale responses immediately; cleanup aborts all request pages.
export function useResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>, delayMs = 0): Resource<T> {
  const [stored, setStored] = useState<StoredResource<T>>({ key: null, result: { status: "idle" } });
  useEffect(() => {
    if (key === null) return;
    setStored({ key, result: { status: "loading" } });
    return startResourceRequest(load, result => setStored({ key, result }), delayMs);
    // The caller supplies a key containing every request parameter.
  }, [key, delayMs]);
  return visibleResource(stored, key);
}
