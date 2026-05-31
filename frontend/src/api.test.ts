import { describe, expect, it, vi } from "vitest";
import { startSession, submitTurn } from "./api";

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

describe("tutor API client", () => {
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
});
