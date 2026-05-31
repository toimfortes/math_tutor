/**
 * Render-safe text for LLM-authored content.
 *
 * React escapes string children by default, so the raw text — including any
 * `<script>` or `<img onerror=...>` payloads a provider might emit — is shown
 * verbatim and never parsed into executable DOM. This component intentionally
 * does NOT use dangerouslySetInnerHTML. It can later be extended to render
 * KaTeX from a parsed, sanitized representation.
 */
export function MathText({ text }: { text: string }) {
  return <span className="math-text">{text}</span>;
}
