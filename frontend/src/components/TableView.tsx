export type TableSpec = {
  inputLabel: string;
  outputLabel: string;
  rows: Array<[number, number]>;
};

/**
 * Renders the public-safe table payload for rate-of-change problems as a plain
 * HTML table. The payload carries only the input/output values the student
 * sees, never the canonical rate, so the table cannot leak the answer.
 */
export function TableView({ table }: { table: TableSpec }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">{table.inputLabel}</th>
          <th scope="col">{table.outputLabel}</th>
        </tr>
      </thead>
      <tbody>
        {table.rows.map(([input, output], index) => (
          <tr key={`row-${index}`}>
            <td>{input}</td>
            <td>{output}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
