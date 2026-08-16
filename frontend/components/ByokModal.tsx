"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, EyeOff, KeyRound, Lock, Server, X } from "lucide-react";

import { useExtractStore } from "@/store/useExtractStore";
import type { LlmProvider } from "@/lib/byok";

interface ByokModalProps {
  open: boolean;
  onClose: () => void;
}

const PROVIDERS: { value: LlmProvider | ""; label: string }[] = [
  { value: "", label: "No provider" },
  { value: "groq", label: "Groq" },
  { value: "openai", label: "OpenAI" },
  { value: "ollama", label: "Ollama (local)" },
];

export function ByokModal({ open, onClose }: ByokModalProps) {
  const {
    provider,
    groqKey,
    openaiKey,
    ollamaEndpoint,
    setProvider,
    setGroqKey,
    setOpenaiKey,
    setOllamaEndpoint,
  } = useExtractStore();

  const [showKeys, setShowKeys] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (open) setSaved(false);
  }, [open]);

  if (!open) return null;

  const save = () => {
    setSaved(true);
    window.setTimeout(() => {
      setSaved(false);
      onClose();
    }, 900);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 8 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 8 }}
          transition={{ type: "spring", stiffness: 300, damping: 26 }}
          onClick={(event) => event.stopPropagation()}
          className="w-full max-w-md rounded-lg border border-zinc-800/80 bg-zinc-900/90 p-6 shadow-orange-glow"
        >
          <div className="mb-5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-orange-500/10 p-1.5 text-orange-400">
                <KeyRound size={16} />
              </span>
              <h2 className="text-sm font-semibold text-zinc-100">BYOK Provider Keys</h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Close settings"
              className="rounded-md p-1 text-zinc-500 transition-colors hover:text-zinc-300"
            >
              <X size={16} />
            </button>
          </div>

          <label className="mb-1.5 block text-xs font-medium text-zinc-400">
            LLM Provider
          </label>
          <select
            value={provider}
            onChange={(event) => setProvider(event.target.value as LlmProvider | "")}
            className="mb-4 w-full rounded-md border border-panel bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:outline-none"
          >
            {PROVIDERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <div className="space-y-3">
            {provider === "groq" && (
              <KeyInput
                label="X-Groq-Key"
                value={groqKey}
                onChange={setGroqKey}
                placeholder="gsk_••••••••"
                show={showKeys}
              />
            )}
            {provider === "openai" && (
              <KeyInput
                label="X-OpenAI-Key"
                value={openaiKey}
                onChange={setOpenaiKey}
                placeholder="sk-••••••••"
                show={showKeys}
              />
            )}
            {provider === "ollama" && (
              <KeyInput
                label="X-Ollama-Endpoint"
                value={ollamaEndpoint}
                onChange={setOllamaEndpoint}
                placeholder="http://localhost:11434"
                show={showKeys}
                showMaskToggle={false}
              />
            )}
          </div>

          {provider !== "ollama" && provider !== "" && (
            <button
              onClick={() => setShowKeys((value) => !value)}
              className="mt-3 flex items-center gap-1.5 text-xs text-zinc-500 transition-colors hover:text-orange-400"
            >
              {showKeys ? <EyeOff size={14} /> : <Eye size={14} />}
              {showKeys ? "Hide keys" : "Show keys"}
            </button>
          )}

          <p className="mt-4 flex items-center gap-1.5 text-xs text-zinc-500">
            <Lock size={12} className="text-orange-500" />
            Keys are encrypted and stored only in your browser. Sent via X-headers to the API —
            never logged or saved server-side.
          </p>

          <div className="mt-5 flex items-center justify-end gap-3">
            {saved && (
              <span className="rounded-full border border-orange-500/20 bg-orange-500/10 px-3 py-1 text-xs text-orange-400">
                Saved to browser
              </span>
            )}
            <button
              onClick={save}
              className="flex items-center gap-1.5 rounded-md bg-orange-500 px-4 py-2 text-sm font-medium text-white shadow-orange-glow transition-colors hover:bg-orange-600"
            >
              <Server size={14} />
              Save Keys
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

interface KeyInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  show: boolean;
  showMaskToggle?: boolean;
}

function KeyInput({
  label,
  value,
  onChange,
  placeholder,
  show,
  showMaskToggle = true,
}: KeyInputProps) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-zinc-400">{label}</label>
      <input
        type={showMaskToggle && show ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        className="w-full rounded-md border border-panel bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:border-orange-500 focus:outline-none"
      />
    </div>
  );
}