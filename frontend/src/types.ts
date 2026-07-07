export interface Span {
  id: string;
  parent_id: string | null;
  name: string;
  kind: string;
  status: string;
  start_ms: number;
  end_ms: number | null;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  tokens: number;
  error: string | null;
}

export interface TraceSummary {
  trace_id: string;
  duration_ms: number;
  span_count: number;
  total_tokens: number;
  spans: Span[];
}

export interface StreamEvent {
  type: "span_start" | "span_end" | "log" | "result" | "error" | "artifact" | "proposal" | "done";
  trace_id?: string;
  span?: Span;
  message?: string;
  result?: unknown;
  trace?: TraceSummary;
  run_id?: string;
  artifact?: Artifact;
  proposal?: Record<string, unknown>;
  session?: ChatSession;
  [k: string]: unknown;
}

export interface Artifact {
  id: string;
  kind: string;
  data: Record<string, unknown>;
  created_at?: number;
}

export interface ChatSession {
  id: string;
  title?: string;
  created_at?: number;
  updated_at?: number;
  messages: { role: string; content: string; ts?: number }[];
  workspace: Record<string, unknown>;
  artifacts: Artifact[];
  pending_proposal?: Record<string, unknown> | null;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  preview: string;
  message_count: number;
  company: string;
  created_at: number;
  updated_at: number;
}

export interface RuntimeSettings {
  llm_mode: "auto" | "offline" | "online";
  llm_enabled: boolean;
  llm_effective_label: string;
  providers_configured: boolean;
  providers: ProviderCatalogItem[];
  provider_priority: string[];
  active_provider?: string | null;
}

export interface ProviderTestResult {
  ok: boolean;
  provider: string;
  model?: string;
  protocol?: string;
  latency_ms?: number;
  reply_preview?: string;
  error?: string;
}

export interface ProviderModelsResult {
  ok: boolean;
  provider: string;
  models: string[];
  error?: string;
}

export interface ProviderCatalogItem {
  name: string;
  protocol: string;
  model: string;
  base_url: string;
  api_key_env: string;
  configured: boolean;
  available: boolean;
  api_key_masked: string | null;
  source: "env" | "ui" | "none";
}

export interface Provider {
  name: string;
  protocol: string;
  model: string;
  available: boolean;
}

export interface Status {
  llm_enabled: boolean;
  llm_mode?: string;
  llm_effective_label?: string;
  providers_configured?: boolean;
  active_provider?: string | null;
  provider_catalog?: ProviderCatalogItem[];
  provider_priority?: string[];
  providers: Provider[];
  tools: string[];
  mcp_notes: string[];
  default_priority: string[];
  app_version?: string;
}

export interface Faithfulness {
  ok: boolean;
  issues: { kind: string; value: string; note: string }[];
}

export interface RewriteSuggestion {
  original: string;
  rewritten: string;
  principles: string[];
  needs_input: string[];
  faithfulness: Faithfulness | null;
}

export interface MatchResult {
  score: number;
  skill_score: number;
  experience_score: number;
  matched_skills: string[];
  missing_required: string[];
  missing_preferred: string[];
  strengths: string[];
  gaps: string[];
  recommendation: string;
  verdict: string;
}

export interface InterviewTurn {
  role: "interviewer" | "candidate";
  content: string;
}

export interface InterviewSession {
  id: string;
  language: string;
  finished: boolean;
  question_count: number;
  max_questions: number;
  turns: InterviewTurn[];
}
