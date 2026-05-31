import type { ReactElement } from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { MathText } from "./MathText";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("MathText", () => {
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

  it("renders a script payload as visible text, not an executable element", () => {
    const container = render(<MathText text={"<script>window.pwned = true</script>"} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>window.pwned = true</script>");
  });

  it("renders an img onerror payload as text, not an image element", () => {
    const container = render(<MathText text={'<img src=x onerror="window.pwned = true">'} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="window.pwned = true">');
  });

  it("renders plain math text", () => {
    const container = render(<MathText text={"slope = rise / run"} />);

    expect(container.textContent).toContain("slope = rise / run");
  });
});
