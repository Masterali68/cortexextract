"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { buildByokHeaders, type ByokKeys, type LlmProvider } from "@/lib/byok";
import { decrypt, encrypt } from "@/lib/crypto";

export type ExtractStatus = "idle" | "extracting" | "done" | "error";
export type ChunkMode = "fixed" | "semantic" | "heading";
export type ActiveTab = "markdown" | "json" | "chunks";
export type ExportFormat = "md" | "json";

export interface ChunkItem {
  content: string;
  start: number;
  end: number;
  token_count: number;
}

export interface TokenMetrics {
  chars: number;
  words: number;
  tokensCl100k: number;
  tokensO200k: number;
}

interface SchemaResponse {
  data: Record<string, unknown>;
}

interface ChunkResponse {
  chunks: ChunkItem[];
}

interface PipelineResponse {
  clean_markdown: string;
  raw_html: string;
  title: string;
  metadata: {
    characters?: number;
    words?: number;
    tokens_cl100k?: number;
    tokens_o200k?: number;
  };
  chunks: ChunkItem[];
  schema_output: Record<string, unknown> | null;
  schema_meta: { provider?: string; model?: string; error?: string | null } | null;
  vector: {
    stored: boolean;
    inserted: number;
    total_documents: number;
    error?: string | null;
  } | null;
}

export interface AskSource {
  content: string;
  title: string;
  source_url: string;
  score: number;
}

interface AskResponse {
  answer: string;
  provider: string;
  model: string;
  sources: AskSource[];
}

interface CrawlResponse {
  success: boolean;
  seed_url: string;
  strategy?: string;
  index_used?: string | null;
  pages_crawled: number;
  chunks_stored: number;
  total_documents: number;
  failures: { url: string; error: string }[];
  elapsed_ms: number;
}

export type AskStatus = "idle" | "asking" | "done" | "error";

interface ExtractStore extends ByokKeys {
  url: string;
  status: ExtractStatus;
  error: string | null;
  cleanMarkdown: string;
  rawHtml: string;
  schemaOutput: Record<string, unknown> | null;
  chunks: ChunkItem[];
  activeTab: ActiveTab;
  metrics: TokenMetrics | null;
  stripNoise: boolean;
  autoSchema: boolean;
  autoStoreVectors: boolean;
  exportFormat: ExportFormat;
  chunkMode: ChunkMode;
  maxPages: number;
  askQuestion: string;
  askStatus: AskStatus;
  askError: string | null;
  askAnswer: string;
  askSources: AskSource[];

  setUrl: (url: string) => void;
  setProvider: (provider: LlmProvider | "") => void;
  setGroqKey: (key: string) => void;
  setOpenaiKey: (key: string) => void;
  setOllamaEndpoint: (endpoint: string) => void;
  setStripNoise: (value: boolean) => void;
  setAutoSchema: (value: boolean) => void;
  setAutoStoreVectors: (value: boolean) => void;
  setExportFormat: (format: ExportFormat) => void;
  setChunkMode: (mode: ChunkMode) => void;
  setActiveTab: (tab: ActiveTab) => void;
  setMaxPages: (pages: number) => void;
  setAskQuestion: (question: string) => void;
  ask: () => Promise<void>;
  extract: () => Promise<void>;
  crawl: () => Promise<void>;
  generateSchema: () => Promise<void>;
  runChunking: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    summary: { type: "string" },
    headings: { type: "array", items: { type: "string" } },
    key_points: { type: "array", items: { type: "string" } },
    links: { type: "array", items: { type: "string" } },
  },
  required: ["title", "summary", "headings", "key_points"],
};

const encryptedStorage = createJSONStorage<Partial<ExtractStore>>(() => ({
  getItem: async (name) => {
    const raw = localStorage.getItem(name);
    if (!raw) return null;
    return decrypt(raw);
  },
  setItem: async (name, value) => {
    localStorage.setItem(name, await encrypt(value));
  },
  removeItem: (name) => localStorage.removeItem(name),
}));

export const useExtractStore = create<ExtractStore>()(
  persist(
    (set, get) => ({
      provider: "",
      groqKey: "",
      openaiKey: "",
      ollamaEndpoint: "",
      url: "",
      status: "idle",
      error: null,
      cleanMarkdown: "",
      rawHtml: "",
      schemaOutput: null,
      chunks: [],
      activeTab: "markdown",
      metrics: null,
      stripNoise: true,
      autoSchema: true,
      autoStoreVectors: true,
      exportFormat: "md",
      chunkMode: "heading",
      maxPages: 25,
      askQuestion: "",
      askStatus: "idle",
      askError: null,
      askAnswer: "",
      askSources: [],

      setUrl: (url) => set({ url }),
      setProvider: (provider) => set({ provider }),
      setGroqKey: (groqKey) => set({ groqKey }),
      setOpenaiKey: (openaiKey) => set({ openaiKey }),
      setOllamaEndpoint: (ollamaEndpoint) => set({ ollamaEndpoint }),
      setStripNoise: (stripNoise) => set({ stripNoise }),
      setAutoSchema: (autoSchema) => set({ autoSchema }),
      setAutoStoreVectors: (autoStoreVectors) => set({ autoStoreVectors }),
      setExportFormat: (exportFormat) => set({ exportFormat }),
      setChunkMode: (chunkMode) => set({ chunkMode }),
      setActiveTab: (activeTab) => set({ activeTab }),
      setMaxPages: (maxPages) => set({ maxPages }),
      setAskQuestion: (askQuestion) => set({ askQuestion }),

      extract: async () => {
        const { url, stripNoise, chunkMode, autoSchema, autoStoreVectors } = get();
        if (!url.trim()) {
          set({ status: "error", error: "Enter a URL to extract." });
          return;
        }
        set({ status: "extracting", error: null });
        try {
          const response = await fetch("http://localhost:8000/api/v1/pipeline", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...buildByokHeaders(get()),
            },
            body: JSON.stringify({
              url,
              render_js: true,
              strip_noise: stripNoise,
              timeout_seconds: 30,
              chunk_mode: chunkMode,
              chunk_max_tokens: 512,
              generate_schema: autoSchema,
              store_vectors: autoStoreVectors,
              schema_max_tokens: 1024,
            }),
          });
          if (!response.ok) {
            const body = await response.text();
            throw new Error(`Extraction failed (${response.status}): ${body}`);
          }
          const data = (await response.json()) as PipelineResponse;
          const m = data.metadata;

          const notices: string[] = [];
          if (data.schema_meta?.error) {
            notices.push(`Schema skipped: ${data.schema_meta.error}`);
          } else if (data.schema_output) {
            notices.push("JSON schema generated.");
          }
          if (data.vector?.error) {
            notices.push(`Vector store skipped: ${data.vector.error}`);
          } else if (data.vector?.stored) {
            if (data.vector.inserted > 0) {
              notices.push(
                `Stored ${data.vector.inserted} chunks (${data.vector.total_documents} total).`,
              );
            } else {
              notices.push(
                `Chunks already stored (${data.vector.total_documents} total) - nothing new to add.`,
              );
            }
          }

          set({
            status: "done",
            cleanMarkdown: data.clean_markdown,
            rawHtml: data.raw_html,
            schemaOutput: data.schema_output ?? null,
            chunks: data.chunks ?? [],
            metrics: {
              chars: m.characters ?? 0,
              words: m.words ?? 0,
              tokensCl100k: m.tokens_cl100k ?? 0,
              tokensO200k: m.tokens_o200k ?? 0,
            },
            activeTab: "markdown",
            error: notices.length > 0 ? notices.join(" ") : null,
          });
        } catch (err) {
          set({
            status: "error",
            error: err instanceof Error ? err.message : "Unknown extraction error",
          });
        }
      },

      crawl: async () => {
        const { url, stripNoise, chunkMode, maxPages, autoStoreVectors } = get();
        if (!url.trim()) {
          set({ status: "error", error: "Enter a URL to crawl." });
          return;
        }
        set({ status: "extracting", error: null });
        try {
          const response = await fetch("http://localhost:8000/api/v1/crawl", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...buildByokHeaders(get()),
            },
            body: JSON.stringify({
              url,
              max_pages: maxPages,
              max_depth: 3,
              use_index: true,
              render_js: true,
              timeout_seconds: 30,
              strip_noise: stripNoise,
              chunk_mode: chunkMode,
              chunk_max_tokens: 512,
              store_vectors: autoStoreVectors,
            }),
          });
          if (!response.ok) {
            const body = await response.text();
            throw new Error(`Crawl failed (${response.status}): ${body}`);
          }
          const data = (await response.json()) as CrawlResponse;
          const failed = data.failures?.length ?? 0;
          const failureNote =
            failed > 0 ? ` ${failed} page${failed === 1 ? "" : "s"} failed.` : "";
          const strategy = data.strategy ?? "bfs";
          const sourceNote = data.index_used
            ? ` via ${data.index_used.replace(/^https?:\/\//, "")}`
            : " (link crawl)";
          set({
            status: "done",
            error: `Crawled ${data.pages_crawled} pages, stored ${data.chunks_stored} chunks (${data.total_documents} total) in ${(data.elapsed_ms / 1000).toFixed(1)}s via ${strategy}${sourceNote}.${failureNote}`,
          });
        } catch (err) {
          set({
            status: "error",
            error: err instanceof Error ? err.message : "Unknown crawl error",
          });
        }
      },

      generateSchema: async () => {
        const { cleanMarkdown } = get();
        if (!cleanMarkdown) {
          set({ status: "error", error: "Extract content first." });
          return;
        }
        set({ status: "extracting", error: null });
        try {
          const response = await fetch("http://localhost:8000/api/v1/schema", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...buildByokHeaders(get()),
            },
            body: JSON.stringify({
              markdown: cleanMarkdown,
              json_schema: DEFAULT_SCHEMA,
              max_tokens: 1024,
            }),
          });
          if (!response.ok) {
            const body = await response.text();
            throw new Error(`Schema extraction failed (${response.status}): ${body}`);
          }
          const data = (await response.json()) as SchemaResponse;
          set({ status: "done", schemaOutput: data.data, activeTab: "json" });
        } catch (err) {
          set({
            status: "error",
            error: err instanceof Error ? err.message : "Unknown schema error",
          });
        }
      },

      runChunking: async () => {
        const { cleanMarkdown, chunkMode } = get();
        if (!cleanMarkdown) return;
        set({ status: "extracting", error: null });
        try {
          const response = await fetch("http://localhost:8000/api/v1/chunk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: cleanMarkdown,
              mode: chunkMode,
              max_tokens: 512,
              overlap: 0.1,
            }),
          });
          if (!response.ok) {
            const body = await response.text();
            throw new Error(`Chunking failed (${response.status}): ${body}`);
          }
          const data = (await response.json()) as ChunkResponse;
          set({ status: "done", chunks: data.chunks, activeTab: "chunks" });
        } catch (err) {
          set({
            status: "error",
            error: err instanceof Error ? err.message : "Unknown chunking error",
          });
        }
      },

ask: async () => {
        const { askQuestion, provider } = get();
        if (!askQuestion.trim()) {
          set({ askStatus: "error", askError: "Enter a question first." });
          return;
        }
        if (!provider) {
          set({
            askStatus: "error",
            askError: "Set an LLM provider (BYOK) before asking.",
          });
          return;
        }
        set({ askStatus: "asking", askError: null, askAnswer: "" });
        try {
          const response = await fetch("http://localhost:8000/api/v1/ask", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...buildByokHeaders(get()),
            },
            body: JSON.stringify({
              question: askQuestion.trim(),
              top_k: 8,
              max_tokens: 1024,
            }),
          });
          if (!response.ok) {
            const body = await response.text();
            throw new Error(`Ask failed (${response.status}): ${body}`);
          }
          const data = (await response.json()) as AskResponse;
          set({
            askStatus: "done",
            askAnswer: data.answer,
            askSources: data.sources,
          });
        } catch (err) {
          set({
            askStatus: "error",
            askError: err instanceof Error ? err.message : "Unknown ask error",
          });
        }
      },

      reset: () =>
        set({
          url: "",
          status: "idle",
          error: null,
          cleanMarkdown: "",
          rawHtml: "",
          schemaOutput: null,
          chunks: [],
          metrics: null,
          activeTab: "markdown",
        }),
    }),
    {
      name: "cortexextract-byok-v1",
      storage: encryptedStorage,
      partialize: (state) => ({
        provider: state.provider,
        groqKey: state.groqKey,
        openaiKey: state.openaiKey,
        ollamaEndpoint: state.ollamaEndpoint,
      }),
    },
  ),
);