export type LlmProvider = "groq" | "openai" | "ollama";

export interface ByokKeys {
  provider: LlmProvider | "";
  groqKey: string;
  openaiKey: string;
  ollamaEndpoint: string;
}

export function buildByokHeaders(keys: ByokKeys): Record<string, string> {
  const headers: Record<string, string> = {};
  if (keys.provider) {
    headers["X-LLM-Provider"] = keys.provider;
  }
  if (keys.groqKey) {
    headers["X-Groq-Key"] = keys.groqKey;
  }
  if (keys.openaiKey) {
    headers["X-OpenAI-Key"] = keys.openaiKey;
  }
  if (keys.ollamaEndpoint) {
    headers["X-Ollama-Endpoint"] = keys.ollamaEndpoint;
  }
  return headers;
}