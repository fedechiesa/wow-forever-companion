import { useEffect, useState } from "react";

import { getBackendHealth } from "./api/backend";

type BackendStatus = "checking" | "available" | "unavailable";

export function App() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    getBackendHealth()
      .then(() => setStatus("available"))
      .catch(() => setStatus("unavailable"));
  }, []);

  return (
    <main className="app-shell">
      <section>
        <p className="eyebrow">WoW Forever Companion</p>
        <h1>Technical foundation</h1>
        <p>
          Backend status: <strong>{status}</strong>
        </p>
      </section>
    </main>
  );
}

