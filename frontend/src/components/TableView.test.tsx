import type { ReactElement } from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { TableView, TableSpec } from "./TableView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const TABLE: TableSpec = {
  inputLabel: "Day",
  outputLabel: "Tanks",
  rows: [
    [0, 50],
    [1, 80],
    [2, 110],
    [3, 140],
  ],
};

describe("TableView", () => {
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

  it("renders a table with the input and output labels as headers", () => {
    const container = render(<TableView table={TABLE} />);

    const table = container.querySelector("table.data-table");
    expect(table).not.toBeNull();
    const headers = Array.from(container.querySelectorAll("th")).map((th) => th.textContent);
    expect(headers).toEqual(["Day", "Tanks"]);
  });

  it("renders one body row per data point with both values", () => {
    const container = render(<TableView table={TABLE} />);

    const bodyRows = container.querySelectorAll("tbody tr");
    expect(bodyRows).toHaveLength(4);
    const firstCells = Array.from(bodyRows[0].querySelectorAll("td")).map((td) => td.textContent);
    expect(firstCells).toEqual(["0", "50"]);
    expect(container.textContent).toContain("140");
  });
});
