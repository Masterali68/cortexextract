"use client";

import { useCallback, useState } from "react";
import Editor from "@monaco-editor/react";
import { Check, ClipboardCopy, Download, FileJson, FileText } from "lucide-react";

import { useExtractStore, type ActiveTab } from "@/store/useExtractStore";

const TABS: { id: ActiveTab; label: string; icon: React.ReactNode }[] = [
  { id: "markdown", label: "Markdown", icon: <FileText size={13} /> },
  { id: "json", label: "JSON", icon: <FileJson size={13} /> },
  { id: "chunks", label: "Chunks", icon: <FileText size={13} /> },
];

export function OutputEditor() {
  const {
    cleanMarkdown,
    schemaOutput,
    chunks,
    activeTab,
    metrics,
    exportFormat,
    setActiveTab,
  } = useExtractStore();
  const [copied, setCopied] = useState(false);

  const currentValue =
    activeTab === "markdown"
      ? cleanMarkdown
      : activeTab === "json"
        ? JSON.stringify(schemaOutput ?? {}, null, 2)
        : chunks.map((chunk, index) => `--- chunk ${index + 1} (${chunk.token_count} tokens) ---\n${chunk.content}`).join("\n\n");

  const copyForPrompt = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(currentValue);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = currentValue;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }, [currentValue]);

  const download = useCallback(() => {
    const isMarkdown = exportFormat === "md";
    const content = isMarkdown ? cleanMarkdown : JSON.stringify(schemaOutput ?? {}, null, 2);
    const blob = new Blob([content], {
      type: isMarkdown ? "text/markdown" : "application/json",
    });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `cortexextract.${exportFormat}`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }, [cleanMarkdown, schemaOutput, exportFormat]);

  const hasContent = cleanMarkdown.length > 0 || chunks.length > 0;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-panel bg-zinc-900/90">
      <div className="flex items-center justify-between gap-2 border-b border-panel px-3 py-2">
        <div className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-orange-500/10 text-orange-400"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {metrics && (
          <span className="rounded-full border border-orange-500/20 bg-orange-500/10 px-3 py-0.5 text-xs text-orange-400">
            {metrics.tokensCl100k.toLocaleString()} cl100k ·{" "}
            {metrics.tokensO200k.toLocaleString()} o200k tokens
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1">
        {!hasContent ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-600">
            <FileText size={28} />
            <p className="text-sm">Extracted markdown will render here.</p>
          </div>
        ) : (
          <Editor
            height="100%"
            language={activeTab === "json" ? "json" : activeTab === "markdown" ? "markdown" : "plaintext"}
            value={currentValue}
            theme="vs-dark"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 13,
              scrollBeyondLastLine: false,
              wordWrap: "on",
              automaticLayout: true,
              lineNumbers: "on",
            }}
          />
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-panel px-3 py-2">
        <button
          onClick={() => void copyForPrompt()}
          disabled={!hasContent}
          className="flex items-center gap-1.5 rounded-md border border-panel bg-zinc-950 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-orange-500/40 hover:text-orange-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {copied ? <Check size={13} className="text-emerald-400" /> : <ClipboardCopy size={13} />}
          {copied ? "Copied!" : "Copy for LLM Prompt"}
        </button>
        <button
          onClick={download}
          disabled={!hasContent}
          className="flex items-center gap-1.5 rounded-md border border-panel bg-zinc-950 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-orange-500/40 hover:text-orange-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Download size={13} />
          Download .{exportFormat}
        </button>
      </div>
    </div>
  );
}