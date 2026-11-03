import { Fragment, type ReactNode } from "react";

/** Splits the last question off the final paragraph, so the tutor's follow-up can be shown on its own. */
export function splitFollowUp(text: string): { body: string; followUp: string | null } {
  const trimmed = text.trimEnd();
  if (!trimmed.endsWith("?")) return { body: text, followUp: null };
  const cut = Math.max(trimmed.lastIndexOf(". "), trimmed.lastIndexOf("! "), trimmed.lastIndexOf("\n"));
  if (cut < 0) return { body: text, followUp: null };
  return { body: trimmed.slice(0, cut + 1), followUp: trimmed.slice(cut + 1).trim() };
}

type CiteProps = { onCite?: (n: number) => void; onHover?: (n: number | null) => void; available: number };

/** Renders the tutor's text: paragraphs, **bold**, and [n] citations as buttons. */
export function RichText({ text, ...cite }: { text: string } & CiteProps) {
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim());
  return (
    <>
      {paragraphs.map((p, i) => (
        <p key={i}>
          {p.split("\n").map((line, j) => (
            <Fragment key={j}>
              {j > 0 && <br />}
              {inline(line, cite)}
            </Fragment>
          ))}
        </p>
      ))}
    </>
  );
}

export function inline(line: string, { onCite, onHover, available }: CiteProps): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*|\[\d+\])/g).map((part, k) => {
    const bold = part.match(/^\*\*(.+)\*\*$/);
    if (bold) return <strong key={k}>{bold[1]}</strong>;
    const ref = part.match(/^\[(\d+)\]$/);
    if (ref && Number(ref[1]) <= available) {
      const n = Number(ref[1]);
      return (
        <button key={k} type="button" className="cite" onClick={() => onCite?.(n)}
          onMouseEnter={() => onHover?.(n)} onMouseLeave={() => onHover?.(null)}
          onFocus={() => onHover?.(n)} onBlur={() => onHover?.(null)}
          aria-label={`Open source ${n}`}>{n}</button>
      );
    }
    return <Fragment key={k}>{part}</Fragment>;
  });
}

export function toMarkdown(entries: { role: string; text: string; sources?: string[] }[]): string {
  const lines = [`# ERM Tutor-AI conversation`, ``, `Saved ${new Date().toLocaleString("en-GB")}`, ``];
  for (const e of entries) {
    lines.push(`**${e.role}:** ${e.text.trim()}`, "");
    if (e.sources?.length) lines.push(...e.sources.map((s) => `> ${s}`), "");
  }
  return lines.join("\n");
}
