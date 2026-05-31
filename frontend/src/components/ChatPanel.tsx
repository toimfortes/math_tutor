import { Sparkles } from "lucide-react";
import { MathText } from "./MathText";

/**
 * Tutor dialogue line. Dialogue comes from the LLM, so it is always rendered
 * through MathText, which escapes raw markup instead of executing it.
 */
export function ChatPanel({ dialogue }: { dialogue: string }) {
  return (
    <div className="tutor-line">
      <Sparkles size={18} />
      <p>
        <MathText text={dialogue} />
      </p>
    </div>
  );
}
