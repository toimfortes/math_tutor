import { useState } from "react";
import type { PracticeCheck, PracticeProblem } from "../api";
import { MathText } from "./MathText";

// Deterministic misconception tags -> a short, targeted nudge. Falls back to a
// generic retry message for unrecognised tags.
const MISCONCEPTION_HINTS: Record<string, string> = {
  inverted_slope: "Looks like rise and run are swapped — slope is the change in y divided by the change in x.",
  sign_error: "Check the sign — does the quantity increase or decrease?",
};

/**
 * The separate "extra practice" pool — approved-generated problems, graded by
 * the backend's code-owned checker. Distinct from the assessment tutor loop.
 * Prompts render through MathText so generated text is shown safely.
 */
export function PracticePanel({
  problems,
  onCheck,
}: {
  problems: PracticeProblem[];
  onCheck: (problemId: string, answer: string) => Promise<PracticeCheck>;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, PracticeCheck>>({});

  async function check(problemId: string) {
    const result = await onCheck(problemId, (answers[problemId] ?? "").trim());
    setResults((current) => ({ ...current, [problemId]: result }));
  }

  if (problems.length === 0) {
    return <p className="practice-empty">No extra practice is available yet.</p>;
  }

  return (
    <div className="practice-panel">
      {problems.map((problem) => {
        const result = results[problem.id];
        const correct = result?.checkResult === "correct";
        const misconception = result && !correct && result.errorTag ? MISCONCEPTION_HINTS[result.errorTag] : null;
        return (
          <div key={problem.id} className="practice-item">
            <p className="eyebrow">
              {problem.skillId} · Level {problem.difficulty}
            </p>
            <p>
              <MathText text={problem.prompt} />
            </p>
            <div className="answer-row">
              <input
                value={answers[problem.id] ?? ""}
                onChange={(event) => setAnswers((current) => ({ ...current, [problem.id]: event.target.value }))}
                placeholder="Your answer"
              />
              <button
                className="secondary"
                type="button"
                onClick={() => void check(problem.id)}
                disabled={!(answers[problem.id] ?? "").trim()}
              >
                Check
              </button>
            </div>
            {result ? (
              <span className={`practice-result ${result.checkResult}`}>
                {correct ? "Correct" : misconception ?? "Not yet — try again"}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
