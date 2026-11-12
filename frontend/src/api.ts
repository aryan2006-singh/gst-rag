import type { QueryRequest, QueryResponse, Variant } from "./types";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      const raw = body.detail;
      detail = typeof raw === "string"
        ? raw
        : Array.isArray(raw)
          ? raw.map((e: any) => e.msg ?? String(e)).join("; ")
          : detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchVariants(): Promise<Variant[]> {
  const response = await fetch("/variants");
  return parseJsonOrThrow<Variant[]>(response);
}

export async function runQuery(request: QueryRequest): Promise<QueryResponse> {
  const response = await fetch("/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonOrThrow<QueryResponse>(response);
}

export interface Health {
  status: string;
  n_chunks?: number;
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/health");
  return parseJsonOrThrow<Health>(response);
}
