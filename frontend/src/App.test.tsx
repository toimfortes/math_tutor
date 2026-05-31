import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function publicProblem(prompt: string, problemId: string, skillId = "lin_plot_point") {
  return {
    prompt,
    ref: { problem_id: problemId, realization_key: "space_logistics" },
    skill_id: skillId,
    answer_type: "ordered_pair",
    checker: "ordered_pair",
    representations: ["text"],
    hint_scaffold: {
      max_safe_hint_level: 2,
      level_0: "Think about the relationship.",
      level_1: "Use the relevant representation.",
      level_2: "Name the operation.",
      level_3: null,
    },
  };
}

function turnResponse(prompt: string, problemId: string) {
  return {
    session_id: "s1",
    public_problem: publicProblem(prompt, problemId),
    dialogue: "Here is the next problem.",
    pedagogical_move: "present_next_problem",
    check_result: null,
    xp_awarded: 0,
    proposed_hint_level: 0,
    guardrail_fires: [],
    diagnostic: null,
  };
}

function skillState(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    skill_id: "lin_plot_point",
    attempt_count: 0,
    contexts_seen: ["space_logistics:text"],
    transfer_passed: false,
    retention_passed: false,
    concept_mastered: false,
    ...overrides,
  };
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }));
}

function button(container: HTMLElement, label: string) {
  const match = Array.from(container.querySelectorAll("button")).find((node) => node.textContent?.includes(label));
  if (!match) throw new Error(`Button not found: ${label}`);
  return match as HTMLButtonElement;
}

describe("App", () => {
  let root: Root | null = null;
  let host: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) {
      act(() => root?.unmount());
    }
    host?.remove();
    root = null;
    host = null;
    vi.restoreAllMocks();
  });

  it("loads skill state and exposes skip, transfer, and retention actions", async () => {
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(jsonResponse(turnResponse("Plot the station at (4, 3).", "lf_p01")))
      .mockReturnValueOnce(jsonResponse(skillState()))
      .mockReturnValueOnce(jsonResponse(turnResponse("Find the slope of this route.", "lf_p02")))
      .mockReturnValueOnce(jsonResponse(skillState({ contexts_seen: ["space_logistics:text", "space_logistics:skip"] })))
      .mockReturnValueOnce(jsonResponse(skillState({ transfer_passed: true })))
      .mockReturnValueOnce(jsonResponse(skillState({ transfer_passed: true, retention_passed: true, concept_mastered: true })));
    vi.stubGlobal("fetch", fetchMock);

    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);

    await act(async () => {
      root?.render(<App />);
    });
    await act(async () => {
      button(host!, "Start").click();
    });

    expect(host.textContent).toContain("Plot the station at (4, 3).");
    expect(host.textContent).toContain("Transfer Pending");
    expect(host.textContent).toContain("Retention Pending");

    await act(async () => {
      button(host!, "Skip").click();
    });
    expect(host.textContent).toContain("Find the slope of this route.");

    await act(async () => {
      button(host!, "Transfer").click();
    });
    expect(host.textContent).toContain("Transfer Passed");

    await act(async () => {
      button(host!, "Retention").click();
    });
    expect(host.textContent).toContain("Retention Passed");
    expect(host.textContent).toContain("Mastered");
    expect(fetchMock).toHaveBeenCalledWith("/api/session/skip", expect.objectContaining({ method: "POST" }));
  });

  it("renders a local graph when the problem uses a graph representation", async () => {
    const graphProblem = {
      prompt: "Read the slope from the graph.",
      ref: { problem_id: "lf_p07", realization_key: "space_logistics" },
      skill_id: "lin_slope_from_graph",
      answer_type: "numeric",
      checker: "numeric",
      representations: ["graph"],
      graph: {
        kind: "line",
        x_min: -1,
        x_max: 5,
        y_min: -1,
        y_max: 6,
        points: [
          [0, 0],
          [1, 2],
        ],
        show_grid: true,
      },
      hint_scaffold: {
        max_safe_hint_level: 2,
        level_0: "Find the rise and the run.",
        level_1: "Slope is rise divided by run.",
        level_2: "Write vertical change over horizontal change.",
        level_3: null,
      },
    };
    const graphTurn = {
      session_id: "s1",
      public_problem: graphProblem,
      dialogue: "Here is the next problem.",
      pedagogical_move: "present_next_problem",
      check_result: null,
      xp_awarded: 0,
      proposed_hint_level: 0,
      guardrail_fires: [],
      diagnostic: null,
    };
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(jsonResponse(graphTurn))
      .mockReturnValueOnce(jsonResponse(skillState({ skill_id: "lin_slope_from_graph" })));
    vi.stubGlobal("fetch", fetchMock);

    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);

    await act(async () => {
      root?.render(<App />);
    });
    await act(async () => {
      button(host!, "Start").click();
    });

    expect(host.querySelector("svg.graph-view")).not.toBeNull();
  });
});
