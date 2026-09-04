import { ArrowLeft, ArrowRight, BookOpen, Check, Crosshair, Eye, Flag, Question } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { api } from "../api";
import { ErrorState, LoadingState } from "../components/LoadingState";
import { MarkdownText } from "../components/MarkdownText";
import { QuizCard } from "../components/QuizCard";
import type { Attempt, Mission, Question as QuestionType, Reference } from "../types";

const beatIcons = [Flag, Eye, Crosshair, Question, BookOpen];

export function MissionView({ missionId, onClose, onComplete }: { missionId: string; onClose: () => void; onComplete: () => void }) {
  const [mission, setMission] = useState<Mission | null>(null);
  const [reference, setReference] = useState<Reference | null>(null);
  const [questions, setQuestions] = useState<QuestionType[]>([]);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [beat, setBeat] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [missionData, attemptData] = await Promise.all([api.mission(missionId), api.startMission(missionId)]);
        const recallIds = missionData.beats.flatMap((item) => item.question_ids ?? []);
        const [referenceData, ...questionData] = await Promise.all([
          api.reference(missionData.citation_id),
          ...recallIds.map(api.question),
        ]);
        if (!active) return;
        setMission(missionData);
        setAttempt(attemptData);
        setBeat(attemptData.current_beat);
        setReference(referenceData as Reference);
        setQuestions(questionData as QuestionType[]);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Mission unavailable.");
      }
    }
    void load();
    return () => { active = false; };
  }, [missionId]);

  async function move(next: number) {
    if (!attempt || !mission) return;
    const bounded = Math.min(4, Math.max(0, next));
    await api.updateBeat(attempt.attempt_id, bounded);
    setBeat(bounded);
    if (bounded === 4) onComplete();
  }

  if (error) return <ErrorState message={error} retry={onClose} />;
  if (!mission || !attempt || !reference) return <LoadingState label="Opening mission evidence" />;
  const current = mission.beats[beat];
  const BeatIcon = beatIcons[beat];

  return (
    <div className="mission-page page-enter">
      <header className="mission-header">
        <button className="icon-button" onClick={onClose} aria-label="Back to campaign"><ArrowLeft size={21} /></button>
        <div><p className="eyebrow">Chapter {mission.chapter} · Mission</p><h1>{mission.title}</h1></div>
        <span className={`evidence-badge evidence-badge--${reference.evidence_class}`}>{reference.evidence_class.replaceAll("_", " ")}</span>
      </header>
      <nav className="beat-track" aria-label="Mission learning beats">
        {mission.beats.map((item, index) => {
          const Icon = beatIcons[index];
          return <button key={item.type} className={index === beat ? "beat beat--active" : index < beat ? "beat beat--done" : "beat"} onClick={() => void move(index)}><span>{index < beat ? <Check size={16} /> : <Icon size={17} />}</span><small>{item.title}</small></button>;
        })}
      </nav>
      <main className="mission-stage">
        <div className="mission-stage__title"><BeatIcon size={25} weight="duotone" /><div><p className="eyebrow">Beat {beat + 1} of 5</p><h2>{current.title}</h2></div></div>
        {current.type === "brief" && <><p className="mission-prompt">Start with the purpose and the boundary—not the service names.</p><div className="brief-card"><h3>Mission objective</h3><p>{mission.summary}</p></div></>}
        {current.type === "explore" && <><p className="mission-prompt">Read the cited evidence. Mark what is proven, configured, or still unknown.</p><MarkdownText content={reference.content} /></>}
        {current.type === "decide" && <div className="decision-board"><h3>Before moving on, locate these three things</h3><ul><li><Check size={18} />The source and target boundary</li><li><Check size={18} />The runtime evidence that proves a handoff</li><li><Check size={18} />One claim that still needs environment proof</li></ul><p>Say the path aloud in one sentence. This turns a diagram into operator memory.</p></div>}
        {current.type === "recall" && (questions.length ? questions.map((question) => <QuizCard key={question.id} question={question} submit={(answer, hints) => api.answer(attempt.attempt_id, question.id, answer, hints)} />) : <p className="empty-copy">This capstone uses the incident simulator for its recall test.</p>)}
        {current.type === "debrief" && <div className="debrief-card"><span>Source-backed debrief</span><h3>{reference.title}</h3><p>{mission.summary}</p><p className="debrief-question">Can you explain what crosses this boundary, what evidence proves it, and what you would check first when it fails?</p></div>}
        <div className="mission-controls">
          <button className="button button--quiet" disabled={beat === 0} onClick={() => void move(beat - 1)}><ArrowLeft size={18} /> Previous</button>
          {beat < 4 ? <button className="button button--primary" onClick={() => void move(beat + 1)}>Next beat <ArrowRight size={18} /></button> : <button className="button button--primary" onClick={onClose}>Return to campaign <Check size={18} /></button>}
        </div>
      </main>
    </div>
  );
}
