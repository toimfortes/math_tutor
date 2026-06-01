import { useState } from "react";
import type { PracticeProblem } from "../api";
import { MathText } from "./MathText";

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
  onCheck: (problemId: string, answer: string) => Promise<string>;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, string>>({});

  async function check(problemId: string) {
    const result = await onCheck(problemId, (answers[problemId] ?? "").trim());
    setResults((current) => ({ ...current, [problemId]: result }));
  }

  if (problems.length === 0) {
    return <p className="practice-empty">No extra practice is available yet.</p>;
  }

  return (
    <div className="practice-panel">
      {problems.map((problem) => (
        <div key={problem.id} className="practice-item">
          <p className="eyebrow">{problem.skillId}</p>
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
          {results[problem.id] ? (
            <span className={`practice-result ${results[problem.id]}`}>
              {results[problem.id] === "correct" ? "Correct" : "Not yet — try again"}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
