import { CheckCircle, Lightbulb, XCircle } from "@phosphor-icons/react";
import { useState } from "react";

import type { AnswerResult, Question } from "../types";

export function QuizCard({ question, submit }: { question: Question; submit: (answer: unknown, hints: number) => Promise<AnswerResult> }) {
  const [answer, setAnswer] = useState<unknown>(question.type === "ordering" ? [] : "");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState(false);

  async function checkAnswer() {
    if ((!answer || (Array.isArray(answer) && answer.length !== question.items?.length)) || busy) return;
    setBusy(true);
    try {
      setResult(await submit(answer, hint ? 1 : 0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="quiz-card" aria-labelledby={`prompt-${question.id}`}>
      <div className="eyebrow">Recall check · {question.type.replaceAll("_", " ")}</div>
      <h3 id={`prompt-${question.id}`}>{question.prompt}</h3>
      {question.type === "ordering" && question.items ? (
        <div className="ordering-builder">
          <div className="ordered-path" aria-label="Your sequence">
            {(answer as string[]).map((item, index) => (
              <button key={item} onClick={() => { setAnswer((answer as string[]).filter((entry) => entry !== item)); setResult(null); }}>
                <b>{index + 1}</b>{item}
              </button>
            ))}
            {!(answer as string[]).length && <p>Choose the first boundary below.</p>}
          </div>
          <div className="sequence-pool">
            {question.items.filter((item) => !(answer as string[]).includes(item)).map((item) => (
              <button key={item} onClick={() => { setAnswer([...(answer as string[]), item]); setResult(null); }}>{item}</button>
            ))}
          </div>
        </div>
      ) : question.options ? (
        <div className="answer-grid">
          {question.options.map((option) => (
            <button
              className={answer === option ? "answer-option answer-option--selected" : "answer-option"}
              key={option}
              onClick={() => { setAnswer(option); setResult(null); }}
            >
              {option.replaceAll("-", " ")}
            </button>
          ))}
        </div>
      ) : (
        <textarea
          aria-label="Your answer"
          placeholder="Explain it in your own words…"
          value={typeof answer === "string" ? answer : ""}
          onChange={(event) => { setAnswer(event.target.value); setResult(null); }}
        />
      )}
      <div className="quiz-actions">
        <button className="button button--quiet" onClick={() => setHint(true)}>
          <Lightbulb size={18} /> Hint
        </button>
        <button className="button button--primary" disabled={!answer || (Array.isArray(answer) && answer.length !== question.items?.length) || busy} onClick={checkAnswer}>
          {busy ? "Checking…" : "Check answer"}
        </button>
      </div>
      {hint && !result && <p className="hint">Use the evidence boundary named in the question; avoid assuming runtime success.</p>}
      {result && (
        <div className={result.correct ? "result result--correct" : "result result--incorrect"} role="status">
          {result.correct ? <CheckCircle size={24} weight="fill" /> : <XCircle size={24} weight="fill" />}
          <div>
            <strong>{result.correct ? "Evidence secured" : "Not yet—use the debrief"}</strong>
            <p>{result.explanation}</p>
            <span>Mastery now {Math.round(result.new_mastery)}%</span>
          </div>
        </div>
      )}
    </section>
  );
}
