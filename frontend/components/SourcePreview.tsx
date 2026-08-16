"use client";

import { useState } from "react";
import Editor from "@monaco-editor/react";
import { Eye, Globe, FileCode2 } from "lucide-react";

import { useExtractStore } from "@/store/useExtractStore";

type SourceTab = "dom" | "rendered";

export function SourcePreview() {
  const { rawHtml, url } = useExtractStore();
  const [tab, setTab] = useState<SourceTab>("dom");

  const hasContent = rawHtml.length > 0;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-panel bg-zinc-900/90">
      <div className="flex items-center justify-between border-b border-panel px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Source
        </span>
        <div className="flex items-center gap-1">
          <TabButton
            active={tab === "dom"}
            onClick={() => setTab("dom")}
            icon={<FileCode2 size={13} />}
            label="Raw DOM"
          />
          <TabButton
            active={tab === "rendered"}
            onClick={() => setTab("rendered")}
            icon={<Eye size={13} />}
            label="Rendered"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {!hasContent ? (
          <EmptyState icon={<Globe size={28} />} message="Extract a page to preview its source." />
        ) : tab === "dom" ? (
          <Editor
            height="100%"
            defaultLanguage="html"
            value={rawHtml}
            theme="vs-dark"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 12,
              scrollBeyondLastLine: false,
              wordWrap: "off",
              automaticLayout: true,
            }}
          />
        ) : (
          <iframe
            srcDoc={rawHtml}
            title={`Rendered preview of ${url}`}
            sandbox=""
            className="h-full w-full border-0 bg-white"
          />
        )}
      </div>
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}

function TabButton({ active, onClick, icon, label }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? "bg-orange-500/10 text-orange-400"
          : "text-zinc-500 hover:text-zinc-300"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function EmptyState({ icon, message }: { icon: React.ReactNode; message: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
      {icon}
      <p className="text-sm">{message}</p>
    </div>
  );
}