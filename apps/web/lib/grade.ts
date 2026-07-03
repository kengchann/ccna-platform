// Client-side grading of a learner's answer against the bundle's answer key.
// This is for the local testing UI; it is not authoritative security (the
// answer key ships to the client). A real deployment grades on the server.

import type { Question } from "./types";

export type Answer =
  | { kind: "choice"; selected: string[] }
  | { kind: "ordering"; order: string[] }
  | { kind: "fill_in_blank"; values: Record<string, string> };

export function emptyAnswer(question: Question): Answer {
  const it = question.interaction;
  switch (it.kind) {
    case "ordering":
      return { kind: "ordering", order: it.items.map((i) => i.id) };
    case "fill_in_blank":
      return { kind: "fill_in_blank", values: {} };
    default:
      return { kind: "choice", selected: [] };
  }
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const bs = new Set(b);
  return a.every((x) => bs.has(x));
}

export function isCorrect(question: Question, answer: Answer): boolean {
  const it = question.interaction;
  if (it.kind === "choice" && answer.kind === "choice") {
    return sameSet(answer.selected, it.correct_option_ids);
  }
  if (it.kind === "ordering" && answer.kind === "ordering") {
    return (
      answer.order.length === it.correct_order.length &&
      answer.order.every((id, i) => id === it.correct_order[i])
    );
  }
  if (it.kind === "fill_in_blank" && answer.kind === "fill_in_blank") {
    return it.blanks.every((blank) => {
      const given = (answer.values[blank.id] ?? "").trim().toLowerCase();
      return blank.accepted.some((a) => a.trim().toLowerCase() === given);
    });
  }
  return false;
}

// Whether the learner has entered enough to submit this question.
export function isAnswered(answer: Answer): boolean {
  switch (answer.kind) {
    case "choice":
      return answer.selected.length > 0;
    case "ordering":
      return true;
    case "fill_in_blank":
      return Object.values(answer.values).some((v) => v.trim().length > 0);
  }
}
