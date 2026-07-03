"use client";

import { useMemo, useState } from "react";

import type { Item, Question } from "@/lib/types";
import { Answer, emptyAnswer, isAnswered, isCorrect } from "@/lib/grade";
import { ContentBlocks } from "./ContentBlocks";

const TYPE_LABELS: Record<string, string> = {
  single_choice: "Single choice",
  multiple_choice: "Multiple choice",
  true_false: "True / False",
  drag_and_drop: "Drag & drop",
  matching: "Matching",
  ordering: "Ordering",
  fill_in_blank: "Fill in the blank",
  scenario: "Scenario",
  case_study: "Case study",
};

function itemText(item: Item): string {
  const first = item.content.find((b) => b.kind === "text" || b.kind === "verbatim");
  return first && "text" in first ? first.text : item.id;
}

export function Quiz({ questions }: { questions: Question[] }) {
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [submitted, setSubmitted] = useState<Record<string, boolean>>({});

  const question = questions[index];
  const answer = answers[question.id] ?? emptyAnswer(question);
  const isSubmitted = submitted[question.id] ?? false;

  const score = useMemo(() => {
    let correct = 0;
    let done = 0;
    for (const q of questions) {
      if (submitted[q.id]) {
        done += 1;
        if (isCorrect(q, answers[q.id] ?? emptyAnswer(q))) correct += 1;
      }
    }
    return { correct, done };
  }, [questions, answers, submitted]);

  function setAnswer(next: Answer) {
    setAnswers((prev) => ({ ...prev, [question.id]: next }));
  }

  function submit() {
    setSubmitted((prev) => ({ ...prev, [question.id]: true }));
  }

  const canSubmit = !isSubmitted && isAnswered(answer);

  return (
    <div className="quiz">
      <header className="quiz-header">
        <div>
          <span className="counter">
            Question {index + 1} of {questions.length}
          </span>
          <span className="qtype">{TYPE_LABELS[question.type] ?? question.type}</span>
        </div>
        <span className="score">
          Score: {score.correct}/{score.done}
        </span>
      </header>

      <article className="card">
        <div className="stem">
          {question.source.label ? (
            <div className="qlabel">{question.source.label}</div>
          ) : null}
          <ContentBlocks blocks={question.stem} />
        </div>

        <div className="interaction">
          <Interaction
            question={question}
            answer={answer}
            submitted={isSubmitted}
            onChange={setAnswer}
          />
        </div>

        {isSubmitted ? (
          <Result question={question} answer={answer} />
        ) : (
          <button className="btn primary" disabled={!canSubmit} onClick={submit}>
            Submit answer
          </button>
        )}
      </article>

      <nav className="quiz-nav">
        <button
          className="btn"
          disabled={index === 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
        >
          ← Previous
        </button>
        <button
          className="btn"
          disabled={index === questions.length - 1}
          onClick={() => setIndex((i) => Math.min(questions.length - 1, i + 1))}
        >
          Next →
        </button>
      </nav>
    </div>
  );
}

function Interaction({
  question,
  answer,
  submitted,
  onChange,
}: {
  question: Question;
  answer: Answer;
  submitted: boolean;
  onChange: (a: Answer) => void;
}) {
  const it = question.interaction;

  if (it.kind === "choice" && answer.kind === "choice") {
    const multi = question.type === "multiple_choice";
    const selected = new Set(answer.selected);
    const correct = new Set(it.correct_option_ids);
    return (
      <ul className="options">
        {it.options.map((opt) => {
          const isSel = selected.has(opt.id);
          const cls = submitted
            ? correct.has(opt.id)
              ? "opt correct"
              : isSel
                ? "opt wrong"
                : "opt"
            : isSel
              ? "opt selected"
              : "opt";
          return (
            <li key={opt.id}>
              <label className={cls}>
                <input
                  type={multi ? "checkbox" : "radio"}
                  name={question.id}
                  disabled={submitted}
                  checked={isSel}
                  onChange={() => {
                    if (multi) {
                      const next = new Set(selected);
                      next.has(opt.id) ? next.delete(opt.id) : next.add(opt.id);
                      onChange({ kind: "choice", selected: [...next] });
                    } else {
                      onChange({ kind: "choice", selected: [opt.id] });
                    }
                  }}
                />
                {opt.label ? <span className="opt-marker">{opt.label}</span> : null}
                <span>{itemText(opt)}</span>
              </label>
            </li>
          );
        })}
      </ul>
    );
  }

  if (it.kind === "ordering" && answer.kind === "ordering") {
    const order = answer.order;
    const byId = new Map(it.items.map((i) => [i.id, i]));
    const move = (from: number, to: number) => {
      if (to < 0 || to >= order.length) return;
      const next = [...order];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      onChange({ kind: "ordering", order: next });
    };
    return (
      <ol className="ordering">
        {order.map((id, i) => (
          <li key={id} className="order-row">
            <span className="order-num">{i + 1}</span>
            <span className="order-text">{itemText(byId.get(id)!)}</span>
            {!submitted ? (
              <span className="order-btns">
                <button className="btn tiny" onClick={() => move(i, i - 1)} disabled={i === 0}>
                  ↑
                </button>
                <button
                  className="btn tiny"
                  onClick={() => move(i, i + 1)}
                  disabled={i === order.length - 1}
                >
                  ↓
                </button>
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    );
  }

  if (it.kind === "fill_in_blank" && answer.kind === "fill_in_blank") {
    return (
      <div className="blanks">
        {it.blanks.map((blank, i) => (
          <label key={blank.id} className="blank">
            <span>Blank {i + 1}</span>
            <input
              type="text"
              disabled={submitted}
              value={answer.values[blank.id] ?? ""}
              onChange={(e) =>
                onChange({
                  kind: "fill_in_blank",
                  values: { ...answer.values, [blank.id]: e.target.value },
                })
              }
            />
          </label>
        ))}
      </div>
    );
  }

  // Matching / drag-and-drop: render the items for review. Interactive
  // widgets for these types are a later iteration.
  return (
    <div className="unsupported">
      <p>Interactive input for this question type is not built yet.</p>
    </div>
  );
}

function Result({ question, answer }: { question: Question; answer: Answer }) {
  const correct = isCorrect(question, answer);
  return (
    <div className={`result ${correct ? "ok" : "no"}`}>
      <strong>{correct ? "Correct" : "Not quite"}</strong>
      {question.explanation.length > 0 ? (
        <div className="explanation">
          <div className="explanation-title">Explanation</div>
          <ContentBlocks blocks={question.explanation} />
        </div>
      ) : null}
    </div>
  );
}
