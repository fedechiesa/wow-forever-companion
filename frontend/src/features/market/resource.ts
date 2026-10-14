export type Resource<T> =
  | { status: "idle" | "loading" }
  | { status: "error"; error: Error }
  | { status: "success"; data: T };
export interface StoredResource<T> { key: string | null; result: Resource<T> }

export function visibleResource<T>(stored: StoredResource<T>, key: string | null): Resource<T> {
  if (key === null) return { status: "idle" };
  return stored.key === key ? stored.result : { status: "loading" };
}

// Scheduling before fetch suppresses requests cancelled by StrictMode effect
// replay. Optional debounce also avoids sending every intermediate input value.
export function startResourceRequest<T>(load: (signal: AbortSignal) => Promise<T>, publish: (result: Resource<T>) => void, delayMs = 0): () => void {
  const controller = new AbortController();
  const run = async () => {
    if (controller.signal.aborted) return;
    try {
      const data = await load(controller.signal);
      if (!controller.signal.aborted) publish({ status: "success", data });
    } catch (error) {
      if (!controller.signal.aborted) publish({ status: "error", error: error instanceof Error ? error : new Error("Error inesperado") });
    }
  };
  const timer = delayMs ? setTimeout(() => { void run(); }, delayMs) : undefined;
  if (!delayMs) void Promise.resolve().then(run);
  return () => { controller.abort(); if (timer !== undefined) clearTimeout(timer); };
}
