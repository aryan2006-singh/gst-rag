export interface Citation {
  chunk_id: string;
  doc_id: string;
  score: number;
  status: "in_force" | "amended" | "superseded" | "unknown";
  snippet: string;
  section: string | null;
  published: string | null;
  stage_scores?: Record<string, number>;
}

export interface QueryTrace {
  stage_latency_ms: Record<string, number>;
  total_ms: number;
  config: string;
  skipped_stages?: string[];
}

export interface QueryResponse {
  question: string;
  rewritten_query: string;
  answer: string | null;
  citations: Citation[];
  trace: QueryTrace;
  warnings: string[];
}

export interface QueryRequest {
  question: string;
  top_k?: number;
  as_of?: string;
  variant?: string;
}

export interface Variant {
  name: string;
  use_bm25: boolean;
  use_dense: boolean;
  rerank: boolean;
  query_rewrite: boolean;
  recency_boost: number;
}
