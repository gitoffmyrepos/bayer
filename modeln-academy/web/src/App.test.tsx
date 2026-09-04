import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { QuizCard } from "./components/QuizCard";

const dashboard = {
  worlds: [
    {
      id: "see-the-system",
      title: "See the System",
      description: "Understand the platform before memorizing names.",
      missions: [
        {
          id: "mission-01",
          title: "Model N and Middleware from Zero",
          chapter: 1,
          summary: "Learn the platform boundary.",
          citation_id: "chapter-1",
          beats: [],
        },
      ],
    },
  ],
  recommended_mission_id: "mission-01",
  mastery: { explain_platform_architecture: 36 },
  completed_missions: [],
};

function response(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(body === undefined ? undefined : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockSignedInApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.endsWith("/api/me")) return response({ id: "user-1", display_name: "Kelvin" });
    if (url.endsWith("/api/dashboard")) return response(dashboard);
    if (url.endsWith("/api/reviews/queue")) return response([]);
    if (url.endsWith("/api/simulations")) return response([]);
    if (init?.method === "POST" && url.includes("/start")) {
      return response({ attempt_id: "attempt-1", current_beat: 0 });
    }
    return response({ detail: { message: "Unexpected test request" } }, 500);
  });
}

afterEach(() => vi.restoreAllMocks());

describe("ModelN Systems Adventure", () => {
  it("turns ordering questions into a click-to-build sequence", async () => {
    const submit = vi.fn().mockResolvedValue({ correct: true, score: 1, new_mastery: 10, explanation: "Correct order", citation_id: "trace" });
    render(<QuizCard question={{ id: "order", type: "ordering", prompt: "Order the path", items: ["SFTP", "S3", "Glue"], mastery_skill: "trace", citation_id: "trace" }} submit={submit} />);

    await userEvent.click(screen.getByRole("button", { name: "SFTP" }));
    await userEvent.click(screen.getByRole("button", { name: "S3" }));
    await userEvent.click(screen.getByRole("button", { name: "Glue" }));
    await userEvent.click(screen.getByRole("button", { name: /check answer/i }));

    expect(submit).toHaveBeenCalledWith(["SFTP", "S3", "Glue"], 0);
  });

  it("offers a private sign-in when no session exists", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      response({ detail: { message: "Sign in to continue." } }, 401),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: /enter the academy/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("renders the campaign map and recommended mission", async () => {
    mockSignedInApi();

    render(<App />);

    expect(await screen.findByText("See the System")).toBeInTheDocument();
    expect(screen.getAllByText("Model N and Middleware from Zero")).toHaveLength(2);
    expect(screen.getByText(/recommended next/i)).toBeInTheDocument();
  });

  it("opens a mission into its five learning beats and cited evidence", async () => {
    const api = mockSignedInApi();
    api.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/missions/mission-01")) {
        return response({
          ...dashboard.worlds[0].missions[0],
          beats: [
            { type: "brief", title: "Why this matters" },
            { type: "explore", title: "See the boundaries" },
            { type: "decide", title: "Choose the next move" },
            { type: "recall", title: "Retrieve from memory", question_ids: ["chapter-1-world"] },
            { type: "debrief", title: "Explain and connect" },
          ],
        });
      }
      if (url.endsWith("/api/references/chapter-1")) {
        return response({ title: "Chapter 1", content: "Model N receives business data through explicit middleware boundaries.", evidence_class: "documented" });
      }
      if (url.endsWith("/api/questions/chapter-1-world")) {
        return response({ id: "chapter-1-world", type: "classification", prompt: "Which world?", options: ["see-the-system", "run-the-engine"], mastery_skill: "architecture", citation_id: "chapter-1" });
      }
      if (init?.method === "POST" && url.endsWith("/api/missions/mission-01/start")) {
        return response({ attempt_id: "attempt-1", current_beat: 0 });
      }
      if (init?.method === "PATCH" && url.endsWith("/api/attempts/attempt-1/beat")) {
        return response({ attempt_id: "attempt-1", current_beat: 1 });
      }
      if (url.endsWith("/api/me")) return response({ id: "user-1", display_name: "Kelvin" });
      if (url.endsWith("/api/dashboard")) return response(dashboard);
      if (url.endsWith("/api/reviews/queue") || url.endsWith("/api/simulations")) return response([]);
      return response({}, 500);
    });

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /begin mission/i }));

    expect(await screen.findByRole("heading", { name: "Why this matters" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /see the boundaries/i }));
    expect(screen.getByText(/explicit middleware boundaries/i)).toBeInTheDocument();
    expect(screen.getByText("Retrieve from memory")).toBeInTheDocument();
  });

  it("searches the evidence atlas and keeps source classification visible", async () => {
    const api = mockSignedInApi();
    api.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/search?q=FGI")) {
        return response([{ id: "atlas:1", title: "FGI 205", text: "Direct sales inbound lineage", kind: "fgi_source_pairs", reference_id: "fgi-205", score: 3 }]);
      }
      if (url.includes("/api/coach?q=FGI")) {
        return response({ grounded: true, answer: "FGI 205 direct sales inbound lineage", citations: ["fgi-205"] });
      }
      if (url.endsWith("/api/me")) return response({ id: "user-1", display_name: "Kelvin" });
      if (url.endsWith("/api/dashboard")) return response(dashboard);
      if (url.endsWith("/api/reviews/queue") || url.endsWith("/api/simulations")) return response([]);
      return response({}, 500);
    });

    render(<App />);
    await userEvent.click((await screen.findAllByRole("button", { name: /evidence atlas/i }))[0]);
    await userEvent.type(screen.getByRole("searchbox"), "FGI");
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));

    await waitFor(() => expect(screen.getByText("FGI 205")).toBeInTheDocument());
    expect(screen.getByText(/source-backed result/i)).toBeInTheDocument();
  });
});
