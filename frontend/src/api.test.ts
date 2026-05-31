import { describe, expect, it, vi } from "vitest";
import { getStudentState, recordRetention, recordTransfer, skipProblem, startSession, submitTurn } from "./api";

function problem(prompt: string, problemId: string) {
  return {
    prompt,
    ref: { problem_id: problemId, realization_key: "space_logistics" },
    skill_id: "lin_plot_point",
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

function graphProblem() {
  return {
    prompt: "Read the slope from the graph.",
    ref: { problem_id: "lf_p07", realization_key: "neutral" },
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
}

function turnPayload(publicProblem: unknown) {
  return {
    session_id: "s1",
    public_problem: publicProblem,
    dialogue: "Here is the next problem.",
    pedagogical_move: "present_next_problem",
    check_result: null,
    xp_awarded: 0,
    proposed_hint_level: 0,
    guardrail_fires: [],
    diagnostic: null,
  };
}

describe("tutor API client", () => {
  it("parses the public-safe graph payload into camelCase", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(turnPayload(graphProblem())), { status: 200 }));

    const started = await startSession(fetchMock, { studentId: "student-1", theme: "neutral" });

    const graph = started.publicProblem.graph;
    expect(graph).not.toBeNull();
    expect(graph?.kind).toBe("line");
    expect(graph?.xMin).toBe(-1);
    expect(graph?.yMax).toBe(6);
    expect(graph?.points).toEqual([
      [0, 0],
      [1, 2],
    ]);
    expect(graph?.showGrid).toBe(true);
  });

  it("leaves graph null for text-only problems", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(turnPayload(problem("Prompt", "lf_p09"))), { status: 200 }));

    const started = await startSession(fetchMock, { studentId: "student-1", theme: "neutral" });

    expect(started.publicProblem.graph).toBeNull();
  });

  it("parses the public-safe table payload into camelCase", async () => {
    const tableProblem = {
      ...problem("Find the rate of change.", "lf_p02"),
      representations: ["table"],
      table: {
        input_label: "Day",
        output_label: "Tanks",
        rows: [
          [0, 50],
          [1, 80],
        ],
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(turnPayload(tableProblem)), { status: 200 }));

    const started = await startSession(fetchMock, { studentId: "student-1", theme: "neutral" });

    const table = started.publicProblem.table;
    expect(table).not.toBeNull();
    expect(table?.inputLabel).toBe("Day");
    expect(table?.outputLabel).toBe("Tanks");
    expect(table?.rows).toEqual([
      [0, 50],
      [1, 80],
    ]);
  });

  it("leaves table null for non-table problems", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(turnPayload(problem("Prompt", "lf_p09"))), { status: 200 }));

    const started = await startSession(fetchMock, { studentId: "student-1", theme: "neutral" });

    expect(started.publicProblem.table).toBeNull();
  });

  it("starts a session and submits a turn", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session_id: "s1",
            public_problem: problem("Prompt", "lf_p01"),
            dialogue: "Here is the next problem.",
            pedagogical_move: "present_next_problem",
            check_result: null,
            xp_awarded: 0,
            proposed_hint_level: 0,
            guardrail_fires: [],
            diagnostic: null,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session_id: "s1",
            public_problem: problem("Next", "lf_p02"),
            dialogue: "Here is the next problem.",
            pedagogical_move: "present_next_problem",
            check_result: "correct",
            xp_awarded: 8,
            proposed_hint_level: 0,
            guardrail_fires: [],
            diagnostic: null,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );

    const started = await startSession(fetchMock, { studentId: "student-1", theme: "space_logistics" });
    const turn = await submitTurn(fetchMock, {
      sessionId: started.sessionId,
      idempotencyKey: "turn-1",
      answer: "(4, 3)",
    });

    expect(started.publicProblem.prompt).toBe("Prompt");
    expect(turn.checkResult).toBe("correct");
    expect(turn.xpAwarded).toBe(8);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/session/start",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("skips a problem and records transfer and retention state", async () => {
    const skillState = {
      skill_id: "lin_plot_point",
      attempt_count: 0,
      contexts_seen: ["space_logistics:grid"],
      transfer_passed: true,
      retention_passed: true,
      concept_mastered: false,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session_id: "s1",
            public_problem: problem("Next", "lf_p02"),
            dialogue: "Here is the next problem.",
            pedagogical_move: "present_next_problem",
            check_result: null,
            xp_awarded: 0,
            proposed_hint_level: 0,
            guardrail_fires: [],
            diagnostic: null,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(skillState), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(skillState), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(skillState), { status: 200 }));

    const skipped = await skipProblem(fetchMock, { sessionId: "s1", reason: "stuck" });
    const transfer = await recordTransfer(fetchMock, {
      sessionId: "s1",
      skillId: "lin_plot_point",
      contextKey: "drone_physics:word",
    });
    const retention = await recordRetention(fetchMock, {
      sessionId: "s1",
      skillId: "lin_plot_point",
      contextKey: "space_logistics:delayed",
    });
    const state = await getStudentState(fetchMock, {
      studentId: "student-1",
      sessionId: "s1",
      skillId: "lin_plot_point",
    });

    expect(skipped.publicProblem.ref.problemId).toBe("lf_p02");
    expect(transfer.transferPassed).toBe(true);
    expect(retention.retentionPassed).toBe(true);
    expect(state.contextsSeen).toContain("space_logistics:grid");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/session/skip",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/student/student-1/state?session_id=s1&skill_id=lin_plot_point",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
