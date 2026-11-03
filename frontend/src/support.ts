/** Which part of a cited passage supports a statement: word overlap, computed in the browser, no model call. */

const STOP = new Set(("the and for are but not you your with that this from have has was were can will what when which " +
  "into than then them they their there these those its it's also more most such only each other some any about " +
  "between does use used using how why who all one two may might could would should our out very just like").split(" "));

export function words(text: string): Set<string> {
  return new Set((text.toLowerCase().match(/[a-z][a-z-]{2,}/g) ?? []).filter((w) => !STOP.has(w)));
}

/** The sentences of an answer that cite passage n, without their citation markers. */
export function statementsCiting(text: string, n: number): string[] {
  return text.split(/(?<=[.!?])\s+|\n+/)
    .filter((s) => s.includes(`[${n}]`))
    .map((s) => s.replace(/\s*\[\d+\]/g, "").trim())
    .filter(Boolean);
}

/** Indices of the passage lines that share the most content words with the statements (at most two). */
export function supportingLines(lines: string[], statements: string[]): Set<number> {
  const claim = words(statements.join(" "));
  if (!claim.size) return new Set();
  const scored = lines.map((line, i) => {
    const w = words(line);
    let shared = 0;
    w.forEach((x) => { if (claim.has(x)) shared += 1; });
    return { i, shared, score: w.size ? shared / Math.sqrt(w.size) : 0 };
  }).filter((s) => s.shared >= 2).sort((a, b) => b.score - a.score);
  return new Set(scored.slice(0, 2).map((s) => s.i));
}
