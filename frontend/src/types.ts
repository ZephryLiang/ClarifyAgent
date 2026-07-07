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
  type: "span_start" | "span_end" | "log" | "result" | "error";
  trace_id?: string;
  span?: Span;
  message?: string;
  result?: unknown;
  trace?: TraceSummary;
  run_id?: string;
  [k: string]: unknown;
}

export interface Provider {
  name: string;
  protocol: string;
  model: string;
  available: boolean;
}

export interface Status {
  llm_enabled: boolean;
  providers: Provider[];
  tools: string[];
  mcp_notes: string[];
  default_priority: string[];
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
