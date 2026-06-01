import type { components } from "./generated/apiSchema";

// Wire (snake_case) shapes generated from the backend OpenAPI schema. Typing the
// mappers against these catches drift between the API contract and the parser at
// compile time. Regenerate with:
//   cd frontend && npm run generate:api
// CI checks drift with:
//   cd frontend && npm run check:api
type WireTurn = components["schemas"]["TurnResponseModel"];
type WireSkill = components["schemas"]["SkillStateModel"];
type WireGraph = components["schemas"]["GraphModel"];
type WireTable = components["schemas"]["TableModel"];
type WireGrid = components["schemas"]["GridModel"];

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

export type GraphSpec = {
  kind: string;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  points: Array<[number, number]>;
  showGrid: boolean;
};

export type TableSpec = {
  inputLabel: string;
  outputLabel: string;
  rows: Array<[number, number]>;
};

export type GridSpec = {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  showGrid: boolean;
};

export type PublicProblem = {
  ref: ProblemRef;
  skillId: string;
  answerType: string;
  checker: string;
  representations: string[];
  prompt: string;
  hintScaffold: HintScaffold;
  graph: GraphSpec | null;
  table: TableSpec | null;
  grid: GridSpec | null;
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
  proposedHintLevel: number;
  guardrailFires: string[];
  diagnostic: Diagnostic | null;
  token: string | null;
};

export type SkillState = {
  skillId: string;
  attemptCount: number;
  contextsSeen: string[];
  transferPassed: boolean;
  retentionPassed: boolean;
  conceptMastered: boolean;
};

type FetchLike = typeof fetch;

export async function registerAccount(
  fetcher: FetchLike,
  params: { studentId: string; password: string },
): Promise<void> {
  const response = await fetcher("/api/auth/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ student_id: params.studentId, password: params.password }),
  });
  // 409 means the account already exists, which is fine — the caller will log in.
  if (!response.ok && response.status !== 409) {
    throw new Error(`Request failed: ${response.status}`);
  }
}

export async function login(
  fetcher: FetchLike,
  params: { studentId: string; password: string },
): Promise<string> {
  const response = await fetcher("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ student_id: params.studentId, password: params.password }),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()).auth_token as string;
}

export async function startSession(
  fetcher: FetchLike,
  params: { theme: string; authToken: string },
): Promise<TurnResponse> {
  return postTurnJson(fetcher, "/api/session/start", { theme: params.theme }, params.authToken);
}

export type PracticeProblem = {
  id: string;
  skillId: string;
  prompt: string;
  answerType: string;
  representations: string[];
  difficulty: number;
};

export async function getPracticeProblems(fetcher: FetchLike, authToken: string): Promise<PracticeProblem[]> {
  const response = await fetcher("/api/practice/problems", { method: "GET", headers: authHeaders(authToken) });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  const raw = await response.json();
  return (raw.problems ?? []).map((problem: any) => ({
    id: problem.id,
    skillId: problem.skill_id,
    prompt: problem.prompt,
    answerType: problem.answer_type,
    representations: problem.representations ?? [],
    difficulty: problem.difficulty ?? 3,
  }));
}

export type PracticeCheck = { checkResult: string; errorTag: string | null };

export async function checkPractice(
  fetcher: FetchLike,
  params: { problemId: string; answer: string; authToken: string },
): Promise<PracticeCheck> {
  const response = await fetcher("/api/practice/check", {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders(params.authToken) },
    body: JSON.stringify({ problem_id: params.problemId, answer: params.answer }),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  const raw = await response.json();
  return { checkResult: raw.check_result, errorTag: raw.diagnostic?.student_error_tag ?? null };
}

export async function submitTurn(
  fetcher: FetchLike,
  params: { sessionId: string; idempotencyKey: string; answer: string; token: string },
): Promise<TurnResponse> {
  return postTurnJson(
    fetcher,
    "/api/turn",
    { session_id: params.sessionId, idempotency_key: params.idempotencyKey, answer: params.answer },
    params.token,
  );
}

export async function skipProblem(
  fetcher: FetchLike,
  params: { sessionId: string; reason: string; token: string },
): Promise<TurnResponse> {
  return postTurnJson(
    fetcher,
    "/api/session/skip",
    { session_id: params.sessionId, reason: params.reason },
    params.token,
  );
}

export async function recordTransfer(
  fetcher: FetchLike,
  params: { sessionId: string; skillId: string; contextKey: string; token: string },
): Promise<SkillState> {
  return postSkillStateJson(
    fetcher,
    "/api/assessment/transfer",
    { session_id: params.sessionId, skill_id: params.skillId, context_key: params.contextKey },
    params.token,
  );
}

export async function recordRetention(
  fetcher: FetchLike,
  params: { sessionId: string; skillId: string; contextKey: string; token: string },
): Promise<SkillState> {
  return postSkillStateJson(
    fetcher,
    "/api/assessment/retention",
    { session_id: params.sessionId, skill_id: params.skillId, context_key: params.contextKey },
    params.token,
  );
}

export async function getStudentState(
  fetcher: FetchLike,
  params: { studentId: string; sessionId: string; skillId: string; token: string },
): Promise<SkillState> {
  const query = new URLSearchParams({
    session_id: params.sessionId,
    skill_id: params.skillId,
  });
  const response = await fetcher(`/api/student/${params.studentId}/state?${query.toString()}`, {
    method: "GET",
    headers: authHeaders(params.token),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return toSkillState(await response.json());
}

function authHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function postTurnJson(fetcher: FetchLike, url: string, body: unknown, token?: string): Promise<TurnResponse> {
  const response = await fetcher(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return toTurnResponse(await response.json());
}

async function postSkillStateJson(fetcher: FetchLike, url: string, body: unknown, token?: string): Promise<SkillState> {
  const response = await fetcher(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return toSkillState(await response.json());
}

function toTurnResponse(raw: WireTurn): TurnResponse {
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
      graph: toGraphSpec(raw.public_problem.graph),
      table: toTableSpec(raw.public_problem.table),
      grid: toGridSpec(raw.public_problem.grid),
      hintScaffold: {
        maxSafeHintLevel: raw.public_problem.hint_scaffold.max_safe_hint_level,
        level0: raw.public_problem.hint_scaffold.level_0,
        level1: raw.public_problem.hint_scaffold.level_1,
        level2: raw.public_problem.hint_scaffold.level_2,
        level3: raw.public_problem.hint_scaffold.level_3 ?? null,
      },
    },
    dialogue: raw.dialogue,
    pedagogicalMove: raw.pedagogical_move,
    checkResult: (raw.check_result ?? null) as TurnResponse["checkResult"],
    xpAwarded: raw.xp_awarded,
    proposedHintLevel: raw.proposed_hint_level,
    guardrailFires: raw.guardrail_fires ?? [],
    diagnostic: raw.diagnostic
      ? {
          studentErrorTag: raw.diagnostic.student_error_tag,
          confidence: raw.diagnostic.confidence,
          matchedPattern: raw.diagnostic.matched_pattern ?? null,
          safeHintLevelCap: raw.diagnostic.safe_hint_level_cap,
        }
      : null,
    token: raw.token ?? null,
  };
}

function toGraphSpec(raw: WireGraph | null | undefined): GraphSpec | null {
  if (!raw) {
    return null;
  }
  return {
    kind: raw.kind,
    xMin: raw.x_min,
    xMax: raw.x_max,
    yMin: raw.y_min,
    yMax: raw.y_max,
    points: raw.points.map((point) => [point[0], point[1]] as [number, number]),
    showGrid: raw.show_grid,
  };
}

function toGridSpec(raw: WireGrid | null | undefined): GridSpec | null {
  if (!raw) {
    return null;
  }
  return {
    xMin: raw.x_min,
    xMax: raw.x_max,
    yMin: raw.y_min,
    yMax: raw.y_max,
    showGrid: raw.show_grid,
  };
}

function toTableSpec(raw: WireTable | null | undefined): TableSpec | null {
  if (!raw) {
    return null;
  }
  return {
    inputLabel: raw.input_label,
    outputLabel: raw.output_label,
    rows: raw.rows.map((row) => [row[0], row[1]] as [number, number]),
  };
}

function toSkillState(raw: WireSkill): SkillState {
  return {
    skillId: raw.skill_id,
    attemptCount: raw.attempt_count,
    contextsSeen: raw.contexts_seen,
    transferPassed: raw.transfer_passed,
    retentionPassed: raw.retention_passed,
    conceptMastered: raw.concept_mastered,
  };
}
