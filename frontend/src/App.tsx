import { ArrowRight, BadgeCheck, CalendarCheck2, CheckCircle2, CircleAlert, FastForward, RotateCcw, Send } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { getStudentState, recordRetention, recordTransfer, SkillState, skipProblem, startSession, submitTurn, TurnResponse } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { GraphView } from "./components/GraphView";

const THEMES = [
  { value: "space_logistics", label: "Space Logistics" },
  { value: "drone_physics", label: "Drone Motion" },
  { value: "neutral", label: "Neutral" },
];

const STUDENT_ID = "local-student";

export function App() {
  const [theme, setTheme] = useState("space_logistics");
  const [answer, setAnswer] = useState("");
  const [turn, setTurn] = useState<TurnResponse | null>(null);
  const [skillState, setSkillState] = useState<SkillState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turnCount, setTurnCount] = useState(0);
  const totalXp = useMemo(() => (turn?.xpAwarded ?? 0), [turn]);

  async function loadSkillState(nextTurn: TurnResponse) {
    const nextState = await getStudentState(fetch, {
      studentId: STUDENT_ID,
      sessionId: nextTurn.sessionId,
      skillId: nextTurn.publicProblem.skillId,
    });
    setSkillState(nextState);
  }

  async function begin(selectedTheme = theme) {
    setBusy(true);
    setError(null);
    try {
      const next = await startSession(fetch, { studentId: STUDENT_ID, theme: selectedTheme });
      setTurn(next);
      setAnswer("");
      setTurnCount(0);
      await loadSkillState(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!turn || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const nextCount = turnCount + 1;
      const next = await submitTurn(fetch, {
        sessionId: turn.sessionId,
        idempotencyKey: `local-${nextCount}`,
        answer: answer.trim(),
      });
      setTurn(next);
      setTurnCount(nextCount);
      setAnswer("");
      await loadSkillState(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit");
    } finally {
      setBusy(false);
    }
  }

  async function skipCurrentProblem() {
    if (!turn) return;
    setBusy(true);
    setError(null);
    try {
      const next = await skipProblem(fetch, { sessionId: turn.sessionId, reason: "student_requested" });
      setTurn(next);
      setAnswer("");
      await loadSkillState(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to skip");
    } finally {
      setBusy(false);
    }
  }

  async function recordAssessment(kind: "transfer" | "retention") {
    if (!turn) return;
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
            })
          : await recordRetention(fetch, {
              sessionId: turn.sessionId,
              skillId: turn.publicProblem.skillId,
              contextKey,
            });
      setSkillState(nextState);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record assessment");
    } finally {
      setBusy(false);
    }
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
        <div className="stat-row">
          <span>XP</span>
          <strong>{totalXp}</strong>
        </div>
        <ProgressPanel skillState={skillState} />
      </aside>

      <section className="workspace">
        {turn ? (
          <>
            <header className="problem-header">
              <div>
                <p className="eyebrow">{turn.publicProblem.skillId}</p>
                <h2>{turn.publicProblem.prompt}</h2>
              </div>
              <Status result={turn.checkResult} />
            </header>

            {turn.publicProblem.representations.includes("graph") && turn.publicProblem.graph ? (
              <div className="graph-panel">
                <GraphView graph={turn.publicProblem.graph} />
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
              <span>{turn.publicProblem.hintScaffold.level0}</span>
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
