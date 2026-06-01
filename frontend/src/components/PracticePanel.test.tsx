import type { ReactElement } from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PracticeProblem } from "../api";
import { PracticePanel } from "./PracticePanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const PROBLEMS: PracticeProblem[] = [
  { id: "candidate:lin_evaluate:0", skillId: "lin_evaluate", prompt: "For y = 2x + 1, find y when x = 3.", answerType: "numeric", representations: ["text"] },
  { id: "candidate:lin_evaluate:1", skillId: "lin_evaluate", prompt: "For y = 3x + 2, find y when x = 4.", answerType: "numeric", representations: ["text"] },
];

describe("PracticePanel", () => {
  let root: Root | null = null;
  let host: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    host?.remove();
    root = null;
    host = null;
  });

  function render(node: ReactElement): HTMLDivElement {
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
    act(() => root?.render(node));
    return host;
  }

  function setValue(el: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  it("lists practice prompts and grades an answer via the supplied checker", async () => {
    const onCheck = vi.fn().mockResolvedValue({ checkResult: "correct", errorTag: null });
    const container = render(<PracticePanel problems={PROBLEMS} onCheck={onCheck} />);

    expect(container.textContent).toContain("For y = 2x + 1, find y when x = 3.");

    const input = container.querySelector("input") as HTMLInputElement;
    await act(async () => setValue(input, "7"));
    await act(async () => {
      const checkButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent === "Check");
      checkButton?.click();
    });

    expect(onCheck).toHaveBeenCalledWith("candidate:lin_evaluate:0", "7");
    expect(container.textContent).toContain("Correct");
  });

  it("shows a targeted misconception hint on a recognised wrong answer", async () => {
    const onCheck = vi.fn().mockResolvedValue({ checkResult: "incorrect", errorTag: "inverted_slope" });
    const container = render(<PracticePanel problems={PROBLEMS} onCheck={onCheck} />);

    const input = container.querySelector("input") as HTMLInputElement;
    await act(async () => setValue(input, "1/2"));
    await act(async () => {
      Array.from(container.querySelectorAll("button")).find((b) => b.textContent === "Check")?.click();
    });

    expect(container.textContent).toContain("rise and run are swapped");
  });

  it("renders an empty-state message when there is no practice", () => {
    const container = render(<PracticePanel problems={[]} onCheck={vi.fn()} />);
    expect(container.textContent).toContain("No extra practice");
  });
});
