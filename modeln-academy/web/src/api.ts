import type {
  AnswerResult,
  Attempt,
  Dashboard,
  Mission,
  Question,
  Reference,
  Review,
  SearchResult,
  SimulationState,
  SimulationSummary,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function csrfCookie(): string {
  const match = document.cookie.split("; ").find((item) => item.startsWith("academy_csrf="));
  return match ? decodeURIComponent(match.split("=", 2)[1]) : "";
}

let csrfToken = sessionStorage.getItem("academy_csrf") ?? csrfCookie();

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") {
    csrfToken ||= csrfCookie();
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(payload?.detail?.message ?? "The academy could not complete that request.", response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<{ id: string; display_name: string }>("/api/me"),
  login: async (username: string, password: string) => {
    const result = await request<{ display_name: string; csrf_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    csrfToken = result.csrf_token;
    sessionStorage.setItem("academy_csrf", csrfToken);
    return result;
  },
  logout: async () => {
    await request<void>("/api/auth/logout", { method: "POST" });
    csrfToken = "";
    sessionStorage.removeItem("academy_csrf");
  },
  dashboard: () => request<Dashboard>("/api/dashboard"),
  mission: (id: string) => request<Mission>(`/api/missions/${encodeURIComponent(id)}`),
  reference: (id: string) => request<Reference>(`/api/references/${encodeURIComponent(id)}`),
  question: (id: string) => request<Question>(`/api/questions/${encodeURIComponent(id)}`),
  startMission: (id: string) => request<Attempt>(`/api/missions/${encodeURIComponent(id)}/start`, { method: "POST" }),
  updateBeat: (attemptId: string, beat: number) =>
    request<Attempt>(`/api/attempts/${encodeURIComponent(attemptId)}/beat`, {
      method: "PATCH",
      body: JSON.stringify({ beat }),
    }),
  answer: (attemptId: string, questionId: string, answer: unknown, hintsUsed = 0) =>
    request<AnswerResult>(`/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}`, {
      method: "POST",
      body: JSON.stringify({ submission_id: crypto.randomUUID(), answer, hints_used: hintsUsed }),
    }),
  reviews: () => request<Review[]>("/api/reviews/queue"),
  reviewAnswer: (questionId: string, answer: unknown) =>
    request<AnswerResult>(`/api/reviews/${encodeURIComponent(questionId)}/answer`, {
      method: "POST",
      body: JSON.stringify({ submission_id: crypto.randomUUID(), answer, hints_used: 0 }),
    }),
  simulations: () => request<SimulationSummary[]>("/api/simulations"),
  startSimulation: (id: string) => request<SimulationState>(`/api/simulations/${encodeURIComponent(id)}/start`, { method: "POST" }),
  advanceSimulation: (runId: string, choiceId: string) =>
    request<SimulationState>(`/api/simulations/runs/${encodeURIComponent(runId)}/choices/${encodeURIComponent(choiceId)}`, { method: "POST" }),
  search: (query: string) => request<SearchResult[]>(`/api/search?q=${encodeURIComponent(query)}&limit=12`),
  coach: (query: string) => request<{ grounded: boolean; answer: string; citations: string[] }>(`/api/coach?q=${encodeURIComponent(query)}`),
};
