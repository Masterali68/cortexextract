"use client";

import { motion } from "framer-motion";
import { PanelLeft } from "lucide-react";

import { SourcePreview } from "@/components/SourcePreview";
import { OutputEditor } from "@/components/OutputEditor";
import { AskPanel } from "@/components/AskPanel";

export function StudioWorkspace() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex min-h-[640px] flex-col gap-3"
    >
      <div className="grid flex-1 grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="flex flex-col overflow-hidden rounded-lg border border-zinc-800/80">
          <div className="flex items-center gap-1.5 border-b border-zinc-800 bg-zinc-900/90 px-3 py-2">
            <PanelLeft size={13} className="text-orange-500" />
            <span className="text-xs font-semibold text-zinc-300">Source Preview</span>
          </div>
          <div className="min-h-0 flex-1">
            <SourcePreview />
          </div>
        </div>

        <div className="flex flex-col overflow-hidden rounded-lg border border-zinc-800/80">
          <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/90 px-3 py-2">
            <span className="text-xs font-semibold text-zinc-300">Output</span>
            <span className="text-xs text-zinc-500">Monaco · read-only</span>
          </div>
          <div className="min-h-0 flex-1">
            <OutputEditor />
          </div>
        </div>
      </div>

      <div className="h-[240px] shrink-0">
        <AskPanel />
      </div>
    </motion.div>
  );
}