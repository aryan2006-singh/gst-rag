import type { QueryRequest, QueryResponse, Variant } from "./types";

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
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
