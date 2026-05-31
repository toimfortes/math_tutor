export type ProblemRef = {
  problemId: string;
  realizationKey: string;
};

export type HintScaffold = {
  maxSafeHintLevel: number;
  level0: string;
  level1: string;
  level2: string;
  level3: string | null;
};

export type PublicProblem = {
  ref: ProblemRef;
  skillId: string;
  answerType: string;
  checker: string;
  representations: string[];
  prompt: string;
  hintScaffold: HintScaffold;
};

export type Diagnostic = {
  studentErrorTag: string;
  confidence: string;
  matchedPattern: string | null;
  safeHintLevelCap: number;
};

export type TurnResponse = {
  sessionId: string;
  publicProblem: PublicProblem;
  dialogue: string;
  pedagogicalMove: string;
  checkResult: "correct" | "incorrect" | "undecidable" | null;
  xpAwarded: number;
  diagnostic: Diagnostic | null;
};

type FetchLike = typeof fetch;

export async function startSession(
  fetcher: FetchLike,
  params: { studentId: string; theme: string },
): Promise<TurnResponse> {
  return postJson(fetcher, "/api/session/start", {
    student_id: params.studentId,
    theme: params.theme,
  });
}

export async function submitTurn(
  fetcher: FetchLike,
  params: { sessionId: string; idempotencyKey: string; answer: string },
): Promise<TurnResponse> {
  return postJson(fetcher, "/api/turn", {
    session_id: params.sessionId,
    idempotency_key: params.idempotencyKey,
    answer: params.answer,
  });
}

async function postJson(fetcher: FetchLike, url: string, body: unknown): Promise<TurnResponse> {
  const response = await fetcher(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return toTurnResponse(await response.json());
}

function toTurnResponse(raw: any): TurnResponse {
  return {
    sessionId: raw.session_id,
    publicProblem: {
      ref: {
        problemId: raw.public_problem.ref.problem_id,
        realizationKey: raw.public_problem.ref.realization_key,
      },
      skillId: raw.public_problem.skill_id,
      answerType: raw.public_problem.answer_type,
      checker: raw.public_problem.checker,
      representations: raw.public_problem.representations,
      prompt: raw.public_problem.prompt,
      hintScaffold: {
        maxSafeHintLevel: raw.public_problem.hint_scaffold.max_safe_hint_level,
        level0: raw.public_problem.hint_scaffold.level_0,
        level1: raw.public_problem.hint_scaffold.level_1,
        level2: raw.public_problem.hint_scaffold.level_2,
        level3: raw.public_problem.hint_scaffold.level_3,
      },
    },
    dialogue: raw.dialogue,
    pedagogicalMove: raw.pedagogical_move,
    checkResult: raw.check_result,
    xpAwarded: raw.xp_awarded,
    diagnostic: raw.diagnostic
      ? {
          studentErrorTag: raw.diagnostic.student_error_tag,
          confidence: raw.diagnostic.confidence,
          matchedPattern: raw.diagnostic.matched_pattern,
          safeHintLevelCap: raw.diagnostic.safe_hint_level_cap,
        }
      : null,
  };
}
