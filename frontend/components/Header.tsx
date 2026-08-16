"use client";

import { useEffect, useState } from "react";
import { Settings, Zap } from "lucide-react";
import { motion } from "framer-motion";

import { ByokModal } from "@/components/ByokModal";

type ServerStatus = "checking" | "online" | "offline";

export function Header() {
  const [status, setStatus] = useState<ServerStatus>("checking");
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const response = await fetch("http://localhost:8000/health", {
          signal: AbortSignal.timeout(3000),
        });
        if (!active) return;
        setStatus(response.ok ? "online" : "offline");
      } catch {
        if (active) setStatus("offline");
      }
    };
    void check();
    const interval = setInterval(check, 30_000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <>
      <header className="flex items-center justify-between border-b border-panel bg-zinc-900/90 px-6 py-4">
        <div className="flex items-center gap-2.5">
          <motion.span
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="rounded-md bg-orange-500/10 p-1.5 text-orange-400 shadow-orange-glow"
          >
            <Zap size={18} />
          </motion.span>
          <h1 className="text-lg font-semibold text-zinc-100">
            CortexExtract{" "}
            <span className="text-orange-500 drop-shadow-[0_0_8px_rgba(255,107,0,0.6)]">
              Studio
            </span>
          </h1>
        </div>

        <div className="flex items-center gap-4">
          <span
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
              status === "online"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                : status === "offline"
                  ? "border-orange-500/30 bg-orange-500/10 text-orange-400"
                  : "border-zinc-700 bg-zinc-800/60 text-zinc-400"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                status === "online"
                  ? "animate-pulse bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]"
                  : status === "offline"
                    ? "bg-orange-500 shadow-orange-glow"
                    : "bg-zinc-500"
              }`}
            />
            {status === "checking" ? "Checking API…" : status === "online" ? "API Online" : "API Offline"}
          </span>

          <button
            onClick={() => setSettingsOpen(true)}
            aria-label="Open BYOK settings"
            className="rounded-md border border-panel bg-zinc-900 p-2 text-zinc-400 transition-colors hover:border-orange-500/40 hover:text-orange-400"
          >
            <Settings size={18} />
          </button>
        </div>
      </header>

      <ByokModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}