export type Passage = {
  id: string; unit: number; unit_title: string; page: number; section: string; text: string; score: number;
};
export type Unit = { unit: number; title: string; chunks: number };
export type Health = { status: string; mode: "tutor" | "demo"; retrieval: string };
export type Label = "course" | "general" | "declined" | "demo";
export type Verdict = "correct" | "partly correct" | "not yet";
export type StreamEvent =
  | { type: "sources"; passages: Passage[] }
  | { type: "token"; text: string }
  | { type: "verdict"; verdict: Verdict | null }
  | { type: "done"; label?: Label; cited: number[]; words: number }
  | { type: "error"; message: string };
export type PracticeQuestion = { question: string; unit: number; seed_id: string };

function sessionId(): string {
  try {
    let id = localStorage.getItem("erm2-session");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("erm2-session", id);
    }
    return id;
  } catch {
    return "anonymous";
  }
}

async function request(path: string, body?: unknown): Promise<Response> {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": sessionId() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let message = `The server answered with status ${res.status}.`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch { /* keep the status message */ }
    throw new Error(message);
  }
  return res;
}

export const getHealth = async () => (await request("/api/health")).json() as Promise<Health>;
export const getUnits = async () => (await request("/api/units")).json() as Promise<Unit[]>;
export const newPracticeQuestion = async (unit: number) =>
  (await request("/api/practice/question", { unit })).json() as Promise<PracticeQuestion>;

/** Reads a server-sent event stream from a POST request. */
export async function stream(path: string, body: unknown, onEvent: (e: StreamEvent) => void) {
  const res = await request(path, body);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const line = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
    }
  }
}
