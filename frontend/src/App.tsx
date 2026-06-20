import { ArrowRight, BadgeCheck, CalendarCheck2, CheckCircle2, CircleAlert, Dumbbell, FastForward, LogIn, RotateCcw, Send } from "lucide-react";
import { FormEvent, useState } from "react";
import {
  checkPractice,
  getPracticeProblems,
  getStudentState,
  login,
  PracticeCheck,
  PracticeProblem,
  recordRetention,
  recordTransfer,
  registerAccount,
  SkillState,
  skipProblem,
  startSession,
  submitTurn,
  TurnResponse,
} from "./api";
import { hintForLevel } from "./hints";
import { ChatPanel } from "./components/ChatPanel";
import { GraphView } from "./components/GraphView";
import { GridView } from "./components/GridView";
import { PracticePanel } from "./components/PracticePanel";
import { TableView } from "./components/TableView";

const THEMES = [
  { value: "space_logistics", label: "Space Logistics" },
  { value: "drone_physics", label: "Drone Motion" },
  { value: "neutral", label: "Neutral" },
];

export function App() {
  const [theme, setTheme] = useState("space_logistics");
  const [answer, setAnswer] = useState("");
  const [turn, setTurn] = useState<TurnResponse | null>(null);
  const [skillState, setSkillState] = useState<SkillState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turnCount, setTurnCount] = useState(0);
  const [totalXp, setTotalXp] = useState(0);
  const [token, setToken] = useState<string | null>(null);
  const [studentId, setStudentId] = useState("");
  const [password, setPassword] = useState("");
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [practiceMode, setPracticeMode] = useState(false);
  const [practiceProblems, setPracticeProblems] = useState<PracticeProblem[]>([]);

  async function enterPractice() {
    if (!authToken) return;
    setBusy(true);
    setError(null);
    try {
      setPracticeProblems(await getPracticeProblems(fetch, authToken));
      setPracticeMode(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load practice");
    } finally {
      setBusy(false);
    }
  }

  async function practiceCheck(problemId: string, answer: string): Promise<PracticeCheck> {
    if (!authToken) return { checkResult: "undecidable", errorTag: null };
    return checkPractice(fetch, { problemId, answer, authToken });
  }

  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (!studentId.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      // Create the account if it is new, then log in either way.
      await registerAccount(fetch, { studentId: studentId.trim(), password });
      const nextAuthToken = await login(fetch, { studentId: studentId.trim(), password });
      setAuthToken(nextAuthToken);
      await begin(theme, nextAuthToken);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  async function loadSkillState(nextTurn: TurnResponse, sessionToken: string) {
    const nextState = await getStudentState(fetch, {
      studentId: studentId.trim(),
      sessionId: nextTurn.sessionId,
      skillId: nextTurn.publicProblem.skillId,
      token: sessionToken,
    });
    setSkillState(nextState);
  }

  async function begin(selectedTheme = theme, auth = authToken) {
    if (!auth) return;
    setBusy(true);
    setError(null);
    try {
      const next = await startSession(fetch, { theme: selectedTheme, authToken: auth });
      setTurn(next);
      setToken(next.token);
      setAnswer("");
      setTurnCount(0);
      setTotalXp(next.xpAwarded);
      await loadSkillState(next, next.token ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!turn || !token || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const nextCount = turnCount + 1;
      const next = await submitTurn(fetch, {
        sessionId: turn.sessionId,
        idempotencyKey: `local-${nextCount}`,
        answer: answer.trim(),
        token,
      });
      setTurn(next);
      setTurnCount(nextCount);
      setTotalXp((current) => current + next.xpAwarded);
      setAnswer("");
      await loadSkillState(next, token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit");
    } finally {
      setBusy(false);
    }
  }

  async function skipCurrentProblem() {
    if (!turn || !token) return;
    setBusy(true);
    setError(null);
    try {
      const next = await skipProblem(fetch, { sessionId: turn.sessionId, reason: "student_requested", token });
      setTurn(next);
      setAnswer("");
      await loadSkillState(next, token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to skip");
    } finally {
      setBusy(false);
    }
  }

  async function recordAssessment(kind: "transfer" | "retention") {
    if (!turn || !token) return;
    setBusy(true);
    setError(null);
    const contextKey = `${turn.publicProblem.ref.realizationKey}:${kind}`;
    try {
      const nextState =
        kind === "transfer"
          ? await recordTransfer(fetch, {
              sessionId: turn.sessionId,
              skillId: turn.publicProblem.skillId,
              contextKey,
              token,
            })
          : await recordRetention(fetch, {
              sessionId: turn.sessionId,
              skillId: turn.publicProblem.skillId,
              contextKey,
              token,
            });
      setSkillState(nextState);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record assessment");
    } finally {
      setBusy(false);
    }
  }

  if (!authToken) {
    return (
      <main className="login-shell">
        <form className="login-card" onSubmit={(event) => void signIn(event)}>
          <p className="eyebrow">Gold slice</p>
          <h1>Linear Functions Tutor</h1>
          <label className="field">
            <span>Student ID</span>
            <input
              value={studentId}
              onChange={(event) => setStudentId(event.target.value)}
              placeholder="e.g. ada"
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>
          <button className="primary" type="submit" disabled={busy || !studentId.trim() || !password}>
            <LogIn size={18} />
            Sign in
          </button>
          {error ? <p className="error">{error}</p> : null}
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Gold slice</p>
          <h1>Linear Functions Tutor</h1>
        </div>
        <label className="field">
          <span>Theme</span>
          <select
            value={theme}
            onChange={(event) => {
              setTheme(event.target.value);
              void begin(event.target.value);
            }}
          >
            {THEMES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button className="primary" type="button" onClick={() => void begin()} disabled={busy}>
          <RotateCcw size={18} />
          Start
        </button>
        <button
          className="secondary"
          type="button"
          onClick={() => (practiceMode ? setPracticeMode(false) : void enterPractice())}
          disabled={busy}
        >
          <Dumbbell size={18} />
          {practiceMode ? "Back to tutor" : "Extra practice"}
        </button>
        <div className="stat-row">
          <span>XP</span>
          <strong>{totalXp}</strong>
        </div>
        <ProgressPanel skillState={skillState} />
      </aside>

      <section className="workspace">
        {practiceMode ? (
          <>
            <header className="problem-header">
              <div>
                <p className="eyebrow">Extra practice</p>
                <h2>Generated practice problems</h2>
              </div>
            </header>
            <PracticePanel problems={practiceProblems} onCheck={practiceCheck} />
          </>
        ) : turn ? (
          <>
            <header className="problem-header">
              <div>
                <p className="eyebrow">{turn.publicProblem.skillId}</p>
                <h2>{turn.publicProblem.prompt}</h2>
              </div>
              <Status result={turn.checkResult} />
            </header>

            {turn.publicProblem.graph ? (
              <div className="graph-panel">
                <GraphView graph={turn.publicProblem.graph} />
              </div>
            ) : null}

            {turn.publicProblem.grid ? (
              <div className="graph-panel">
                <GridView grid={turn.publicProblem.grid} />
              </div>
            ) : null}

            {turn.publicProblem.representations.includes("table") && turn.publicProblem.table ? (
              <div className="table-panel">
                <TableView table={turn.publicProblem.table} />
              </div>
            ) : null}

            <div className="problem-actions">
              <button className="secondary" type="button" onClick={() => void skipCurrentProblem()} disabled={busy}>
                <FastForward size={18} />
                Skip
              </button>
              <button className="secondary" type="button" onClick={() => void recordAssessment("transfer")} disabled={busy}>
                <BadgeCheck size={18} />
                Transfer
              </button>
              <button className="secondary" type="button" onClick={() => void recordAssessment("retention")} disabled={busy}>
                <CalendarCheck2 size={18} />
                Retention
              </button>
            </div>

            <ChatPanel dialogue={turn.dialogue} />

            <form className="answer-row" onSubmit={(event) => void submit(event)}>
              <input
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="Type your answer"
                disabled={busy}
              />
              <button className="icon-button" type="submit" disabled={busy || !answer.trim()} aria-label="Submit answer">
                <Send size={18} />
              </button>
            </form>

            <div className="hint-band">
              <ArrowRight size={16} />
              <span>{hintForLevel(turn.publicProblem.hintScaffold, turn.proposedHintLevel)}</span>
            </div>
          </>
        ) : (
          <div className="empty-state">
            <h2>Start a gold-set session</h2>
            <button className="primary" type="button" onClick={() => void begin()} disabled={busy}>
              <ArrowRight size={18} />
              Start
            </button>
          </div>
        )}
        {error ? <p className="error">{error}</p> : null}
      </section>
    </main>
  );
}

function ProgressPanel({ skillState }: { skillState: SkillState | null }) {
  const transfer = skillState?.transferPassed ? "Passed" : "Pending";
  const retention = skillState?.retentionPassed ? "Passed" : "Pending";
  const mastery = skillState?.conceptMastered ? "Mastered" : "In progress";
  return (
    <div className="progress-panel">
      <p className="eyebrow">Progress</p>
      <div className="progress-row">
        <span>Transfer {transfer}</span>
        <strong>{skillState?.attemptCount ?? 0}</strong>
      </div>
      <div className="progress-row">
        <span>Retention {retention}</span>
        <strong>{skillState?.contextsSeen.length ?? 0}</strong>
      </div>
      <div className="progress-row">
        <span>{mastery}</span>
      </div>
    </div>
  );
}

function Status({ result }: { result: TurnResponse["checkResult"] }) {
  if (result === "correct") {
    return (
      <span className="status correct">
        <CheckCircle2 size={18} />
        Correct
      </span>
    );
  }
  if (result === "incorrect") {
    return (
      <span className="status incorrect">
        <CircleAlert size={18} />
        Check
      </span>
    );
  }
  return <span className="status">Ready</span>;
}
