import { ArrowRight, CheckCircle2, CircleAlert, RotateCcw, Send, Sparkles } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { startSession, submitTurn, TurnResponse } from "./api";

const THEMES = [
  { value: "space_logistics", label: "Space Logistics" },
  { value: "drone_physics", label: "Drone Motion" },
  { value: "neutral", label: "Neutral" },
];

export function App() {
  const [theme, setTheme] = useState("space_logistics");
  const [answer, setAnswer] = useState("");
  const [turn, setTurn] = useState<TurnResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turnCount, setTurnCount] = useState(0);
  const totalXp = useMemo(() => (turn?.xpAwarded ?? 0), [turn]);

  async function begin(selectedTheme = theme) {
    setBusy(true);
    setError(null);
    try {
      const next = await startSession(fetch, { studentId: "local-student", theme: selectedTheme });
      setTurn(next);
      setAnswer("");
      setTurnCount(0);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit");
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

            <div className="tutor-line">
              <Sparkles size={18} />
              <p>{turn.dialogue}</p>
            </div>

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
