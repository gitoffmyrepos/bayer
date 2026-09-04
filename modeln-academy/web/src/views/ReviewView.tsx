import { Brain, CalendarCheck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { api } from "../api";
import { LoadingState } from "../components/LoadingState";
import { QuizCard } from "../components/QuizCard";
import type { Question, Review } from "../types";

export function ReviewView({ initialReviews }: { initialReviews: Review[] }) {
  const [reviews, setReviews] = useState(initialReviews);
  const [question, setQuestion] = useState<Question | null>(null);

  useEffect(() => {
    if (!reviews.length) return;
    void api.question(reviews[0].question_id).then(setQuestion);
  }, [reviews]);

  if (!reviews.length) return <div className="review-empty page-enter"><CalendarCheck size={44} weight="duotone" /><p className="eyebrow">Daily review</p><h1>Your memory queue is clear</h1><p>Complete a mission and the learning engine will schedule the right concepts before they fade.</p></div>;
  if (!question) return <LoadingState label="Selecting your weakest memory" />;

  return (
    <div className="review-page page-enter">
      <header className="page-header"><div><p className="eyebrow">Daily review</p><h1>Strengthen the trace</h1><p>{reviews.length} retrieval prompt{reviews.length === 1 ? "" : "s"} queued by the spacing engine.</p></div><Brain size={40} weight="duotone" /></header>
      <div className="review-meter"><span style={{ width: `${100 / reviews.length}%` }} /><small>One focused answer at a time</small></div>
      <QuizCard question={question} submit={async (answer) => {
        const result = await api.reviewAnswer(question.id, answer);
        setReviews((current) => current.slice(1));
        setQuestion(null);
        return result;
      }} />
    </div>
  );
}
