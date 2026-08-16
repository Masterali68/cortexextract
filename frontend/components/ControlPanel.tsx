"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Braces, Database, FileText, Link2, Loader2, ScanSearch, Sparkles } from "lucide-react";

import { useExtractStore, type ChunkMode, type ExportFormat } from "@/store/useExtractStore";

type Mode = "single" | "site";

export function ControlPanel() {
  const {
    url,
    status,
    error,
    stripNoise,
    autoSchema,
    autoStoreVectors,
    exportFormat,
    chunkMode,
    maxPages,
    setUrl,
    setStripNoise,
    setAutoSchema,
    setAutoStoreVectors,
    setExportFormat,
    setChunkMode,
    setMaxPages,
    extract,
    crawl,
  } = useExtractStore();

  const [mode, setMode] = useState<Mode>("single");

  const isBusy = status === "extracting";

  const run = () => {
    if (mode === "site") void crawl();
    else void extract();
  };

  return (
    <div className="space-y-4 rounded-lg border border-panel bg-zinc-900/90 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") run();
          }}
          placeholder={
            mode === "site"
              ? "https://example.com — start crawling from any page"
              : "https://example.com/article"
          }
          disabled={isBusy}
          className="min-w-0 flex-1 rounded-md border border-panel bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-orange-500 focus:outline-none disabled:opacity-60"
        />

        <motion.button
          whileHover={{ scale: isBusy ? 1 : 1.02 }}
          whileTap={{ scale: isBusy ? 1 : 0.98 }}
          onClick={run}
          disabled={isBusy}
          className="flex items-center gap-2 rounded-md bg-orange-500 px-5 py-2.5 text-sm font-semibold text-white shadow-orange-glow transition-colors hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isBusy ? (
            <Loader2 size={16} className="animate-spin" />
          ) : mode === "site" ? (
            <Link2 size={16} />
          ) : (
            <ScanSearch size={16} />
          )}
          {isBusy
            ? mode === "site"
              ? "Crawling…"
              : "Extracting…"
            : mode === "site"
              ? "Crawl Site"
              : "Extract All"}
        </motion.button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-0.5 rounded-full border border-zinc-800 bg-zinc-950 p-0.5">
          {(
            [
              ["single", "Single Page"],
              ["site", "Whole Site"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              disabled={isBusy}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors disabled:opacity-60 ${
                mode === value
                  ? "bg-orange-500/10 text-orange-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === "site" && (
          <div className="flex items-center gap-1 rounded-md border border-panel bg-zinc-950 px-2 py-1">
            <FileText size={12} className="text-zinc-500" />
            <input
              type="number"
              min={1}
              max={100}
              value={maxPages}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                setMaxPages(Number.isFinite(parsed) ? Math.min(100, Math.max(1, parsed)) : 25);
              }}
              disabled={isBusy}
              title="Max pages to crawl"
              className="w-14 bg-transparent text-xs text-zinc-100 focus:outline-none disabled:opacity-60"
            />
            <span className="text-xs text-zinc-500">pages</span>
          </div>
        )}

        <ToggleChip
          active={stripNoise}
          disabled={isBusy}
          onClick={() => setStripNoise(!stripNoise)}
          label="Strip Noise"
        />
        {mode === "single" && (
          <ToggleChip
            active={autoSchema}
            disabled={isBusy}
            onClick={() => setAutoSchema(!autoSchema)}
            label="Schema"
            icon={<Braces size={12} />}
          />
        )}
        <ToggleChip
          active={autoStoreVectors}
          disabled={isBusy}
          onClick={() => setAutoStoreVectors(!autoStoreVectors)}
          label="Store Vectors"
          icon={<Database size={12} />}
        />

        <div className="flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950 p-0.5">
          {(["md", "json"] as ExportFormat[]).map((format) => (
            <button
              key={format}
              onClick={() => setExportFormat(format)}
              disabled={isBusy}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors disabled:opacity-60 ${
                exportFormat === format
                  ? "bg-orange-500/10 text-orange-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {format === "md" ? ".md" : ".json"}
            </button>
          ))}
        </div>

        <select
          value={chunkMode}
          onChange={(event) => setChunkMode(event.target.value as ChunkMode)}
          disabled={isBusy}
          className="rounded-md border border-panel bg-zinc-950 px-3 py-1.5 text-xs text-zinc-100 focus:border-orange-500 focus:outline-none disabled:opacity-60"
        >
          <option value="fixed">Fixed Tokens</option>
          <option value="semantic">Semantic</option>
          <option value="heading">Headings</option>
        </select>

        <span className="ml-auto flex items-center gap-1.5 text-xs text-zinc-500">
          <FileText size={12} />
          {status === "done" ? "Ready" : status === "error" ? "Failed" : status === "extracting" ? "Working…" : "Idle"}
        </span>
      </div>

      {mode === "site" && (
        <p className="flex items-center gap-1.5 text-xs text-zinc-500">
          <Sparkles size={12} className="text-orange-400" />
          Auto-discovers the site index (llms.txt / sitemap.xml) to crawl the whole site; falls
          back to link-following if none exists.
        </p>
      )}

      {error && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-md border px-3 py-2 text-sm ${
            status === "error"
              ? "border-red-500/30 bg-red-500/10 text-red-400"
              : "border-orange-500/20 bg-orange-500/10 text-orange-400"
          }`}
        >
          {error}
        </motion.div>
      )}
    </div>
  );
}

interface ToggleChipProps {
  active: boolean;
  disabled: boolean;
  onClick: () => void;
  label: string;
  icon?: React.ReactNode;
}

function ToggleChip({ active, disabled, onClick, label, icon }: ToggleChipProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        active
          ? "border-orange-500/20 bg-orange-500/10 text-orange-400"
          : "border-zinc-800 bg-zinc-950 text-zinc-500 hover:text-zinc-300"
      }`}
    >
      {icon ?? (
        <motion.span
          layout
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
          className={`h-3.5 w-3.5 rounded-full border ${
            active
              ? "border-orange-500 bg-orange-500 shadow-orange-glow"
              : "border-zinc-600 bg-zinc-800"
          }`}
        />
      )}
      {label}
    </button>
  );
}