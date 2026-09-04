import { ArrowRight, Crosshair, ShieldWarning, Trophy } from "@phosphor-icons/react";
import { useState } from "react";

import { api } from "../api";
import type { SimulationState, SimulationSummary } from "../types";

export function SimulationView({ simulations }: { simulations: SimulationSummary[] }) {
  const [state, setState] = useState<SimulationState | null>(null);
  const [busy, setBusy] = useState(false);

  async function start(id: string) {
    setBusy(true);
    try { setState(await api.startSimulation(id)); } finally { setBusy(false); }
  }

  async function choose(choiceId: string) {
    if (!state) return;
    setBusy(true);
    try { setState(await api.advanceSimulation(state.run_id, choiceId)); } finally { setBusy(false); }
  }

  return (
    <div className="incident-page page-enter">
      <header className="page-header page-header--incident"><div><p className="eyebrow">Incident simulator</p><h1>Practice under uncertainty</h1><p>Choose the next evidence check. Unsafe assumptions cost points; disciplined boundaries earn them.</p></div><ShieldWarning size={42} weight="duotone" /></header>
      {!state ? <div className="scenario-grid">{simulations.map((simulation, index) => <article className="scenario-card" key={simulation.id}><span className="scenario-number">Case {String(index + 1).padStart(2, "0")}</span><Crosshair size={29} weight="duotone" /><h2>{simulation.title}</h2><p>A branching operator drill grounded in the study guide’s incident evidence.</p><button className="button button--incident" disabled={busy} onClick={() => void start(simulation.id)}>Enter simulation <ArrowRight size={18} /></button></article>)}</div> : <section className="incident-console"><div className="incident-score"><span>Evidence score</span><strong>{state.score}</strong></div><div className="incident-status"><span className="status-dot" /> Active case · {state.state_id.replaceAll("-", " ")}</div><h2>{state.prompt}</h2>{state.terminal ? <div className="terminal-state"><Trophy size={34} weight="duotone" /><p>{state.score >= 0 ? "You protected the evidence boundary." : "Review the debrief before retrying."}</p><button className="button button--incident" onClick={() => setState(null)}>Choose another case</button></div> : <div className="choice-list">{state.choices.map((choice) => <button key={choice.id} disabled={busy} onClick={() => void choose(choice.id)}><span>{choice.label}</span><ArrowRight size={19} /></button>)}</div>}</section>}
      {!simulations.length && !state && <div className="state-panel"><p>Incident cases are being prepared.</p></div>}
    </div>
  );
}
