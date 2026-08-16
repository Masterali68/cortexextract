"use client";

import { useState } from "react";
import { Bot, Loader2, MessageSquare, Search } from "lucide-react";

import { useExtractStore } from "@/store/useExtractStore";

export function AskPanel() {
  const {
    askQuestion,
    askStatus,
    askError,
    askAnswer,
    askSources,
    setAskQuestion,
    ask,
  } = useExtractStore();
  const [expandedSource, setExpandedSource] = useState<number | null>(null);

  const canAsk = askQuestion.trim().length > 0 && askStatus !== "asking";

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-zinc-800/80 bg-zinc-900/90">
      <div className="flex items-center gap-1.5 border-b border-zinc-800 px-3 py-2">
        <MessageSquare size={13} className="text-orange-500" />
        <span className="text-xs font-semibold text-zinc-300">Ask your content</span>
        <span className="text-xs text-zinc-500">· RAG over the vector store</span>
      </div>

      <div className="flex gap-2 border-b border-zinc-800 p-3">
        <input
          value={askQuestion}
          onChange={(e) => setAskQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canAsk) void ask();
          }}
          placeholder="Ask a question about anything you've stored..."
          className="min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-orange-500/50 focus:outline-none"
        />
        <button
          onClick={() => void ask()}
          disabled={!canAsk}
          className="flex items-center gap-1.5 rounded-md bg-orange-500 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {askStatus === "asking" ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Search size={13} />
          )}
          {askStatus === "asking" ? "Thinking..." : "Ask"}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {askError && (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {askError}
          </div>
        )}

        {askStatus !== "idle" && askAnswer && (
          <div className="mb-3">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-orange-400">
              <Bot size={13} />
              Answer
            </div>
            <p className="whitespace-pre-wrap rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm leading-relaxed text-zinc-200">
              {askAnswer}
            </p>
          </div>
        )}

        {askSources.length > 0 && (
          <div>
            <div className="mb-1 text-xs font-semibold text-zinc-400">
              Sources ({askSources.length})
            </div>
            <ul className="space-y-1.5">
              {askSources.map((source, index) => (
                <li key={index} className="overflow-hidden rounded-md border border-zinc-800">
                  <button
                    onClick={() => setExpandedSource(expandedSource === index ? null : index)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-zinc-800/40"
                  >
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-zinc-300">
                      {source.title || source.source_url || `Source ${index + 1}`}
                    </span>
                    <span className="shrink-0 rounded-full bg-orange-500/10 px-2 py-0.5 text-[10px] text-orange-400">
                      {Math.round(source.score * 100)}%
                    </span>
                  </button>
                  {expandedSource === index && (
                    <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap border-t border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
                      {source.content}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {askStatus === "idle" && !askError && (
          <p className="text-center text-xs text-zinc-600">
            Hit &ldquo;Extract All&rdquo; to store chunks, then ask questions about them.
          </p>
        )}
      </div>
    </div>
  );
}