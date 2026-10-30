import type {
  AnalyticsOverview,
  AnswerSaved,
  AnswerUpdate,
  AttemptResult,
  AttemptSession,
  AttemptStatus,
  AttemptSummary,
  GenerateTestInput,
  GenerateTestResponse,
  HealthStatus,
  PdfExportOptions,
  SubmitReason,
  TestDetail,
  TestStatus,
  TestSummary,
  TestWrite,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

/** Error raised for any failed API call. `status` 0 means the network request itself failed. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code = "error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  get isNetworkError() {
    return this.status === 0;
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as ValidationIssue;
    const field = first.loc?.filter((part) => part !== "body").join(" → ");
    const msg = (first.msg ?? "Invalid input").replace(/^Value error, /, "");
    return field ? `${field}: ${msg}` : msg;
  }
  return null;
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Can't reach the server. Check your connection and that the backend is running.", 0, "network");
  }
  if (!response.ok) {
    let data: { detail?: unknown; code?: string } = {};
    try {
      data = (await response.json()) ?? {};
    } catch {
      // non-JSON error body
    }
    const message =
      formatDetail(data.detail) ??
      (response.status >= 500 ? "The server ran into a problem. Please try again." : `Request failed (${response.status}).`);
    throw new ApiError(message, response.status, data.code ?? (response.status === 422 ? "invalid_input" : "error"));
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("The server sent an unexpected response.", response.status, "bad_response");
  }
}

function filenameFrom(response: Response, fallback: string) {
  const header = response.headers.get("Content-Disposition") ?? "";
  return /filename="?([^";]+)"?/.exec(header)?.[1] ?? fallback;
}

const json = (method: string, payload?: unknown): RequestInit => ({
  method,
  body: payload === undefined ? undefined : JSON.stringify(payload),
});

function query(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  health: () => request<HealthStatus>("/api/health"),

  listTests: (params: { search?: string; status?: TestStatus | "" } = {}) =>
    request<TestSummary[]>(`/api/tests${query(params)}`),
  getTest: (id: number) => request<TestDetail>(`/api/tests/${id}`),
  createTest: (payload: TestWrite) => request<TestDetail>("/api/tests", json("POST", payload)),
  updateTest: (id: number, payload: TestWrite) => request<TestDetail>(`/api/tests/${id}`, json("PUT", payload)),
  deleteTest: (id: number) => request<void>(`/api/tests/${id}`, { method: "DELETE" }),
  duplicateTest: (id: number) => request<TestDetail>(`/api/tests/${id}/duplicate`, { method: "POST" }),
  generateTest: (input: GenerateTestInput, signal?: AbortSignal) => {
    const form = new FormData();
    for (const [key, value] of Object.entries(input)) {
      if (key === "file" || value === undefined || value === null || value === "") continue;
      form.append(key, String(value));
    }
    if (input.file) form.append("file", input.file);
    return request<GenerateTestResponse>("/api/tests/generate", { method: "POST", body: form, signal });
  },

  pdfDefaults: (id: number) => request<PdfExportOptions>(`/api/tests/${id}/pdf/defaults`),
  downloadPdf: async (id: number, options: PdfExportOptions) => {
    const response = await send(`/api/tests/${id}/pdf`, {
      method: "POST",
      body: JSON.stringify(options),
      headers: { Accept: "application/pdf", "Content-Type": "application/json" },
    });
    return { blob: await response.blob(), filename: filenameFrom(response, `test-${id}.pdf`) };
  },

  startAttempt: (testId: number) => request<AttemptSession>(`/api/tests/${testId}/attempts`, { method: "POST" }),
  getAttempt: (id: string) => request<AttemptSession>(`/api/attempts/${encodeURIComponent(id)}`),
  saveAnswer: (id: string, position: number, payload: AnswerUpdate) =>
    request<AnswerSaved>(`/api/attempts/${encodeURIComponent(id)}/answers/${position}`, json("PUT", payload)),
  submitAttempt: (
    id: string,
    payload: { reason: SubmitReason; answers: (AnswerUpdate & { position: number })[] },
  ) => request<AttemptResult>(`/api/attempts/${encodeURIComponent(id)}/submit`, json("POST", payload)),
  getResult: (id: string) => request<AttemptResult>(`/api/attempts/${encodeURIComponent(id)}/result`),
  listAttempts: (params: { test_id?: number; status?: AttemptStatus | ""; limit?: number } = {}) =>
    request<AttemptSummary[]>(`/api/attempts${query(params)}`),
  deleteAttempt: (id: string) => request<void>(`/api/attempts/${encodeURIComponent(id)}`, { method: "DELETE" }),

  analytics: () => request<AnalyticsOverview>("/api/analytics"),
};
