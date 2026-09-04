import { ArrowRight, CheckCircle, Compass, Lightning, Path, Trophy } from "@phosphor-icons/react";

import type { Dashboard, Mission } from "../types";

const worldNumbers: Record<string, string> = {
  "see-the-system": "01",
  "follow-inbound": "02",
  "run-the-engine": "03",
  "shape-the-data": "04",
  "close-the-loop": "05",
  "operate-safely": "06",
  "incident-capstone": "07",
};

export function DashboardView({ data, reviews, onMission }: { data: Dashboard; reviews: number; onMission: (mission: Mission) => void }) {
  const allMissions = data.worlds.flatMap((world) => world.missions);
  const recommended = allMissions.find((mission) => mission.id === data.recommended_mission_id) ?? allMissions[0];
  const completed = new Set(data.completed_missions);
  const masteryValues = Object.values(data.mastery);
  const mastery = masteryValues.length ? Math.round(masteryValues.reduce((sum, score) => sum + score, 0) / masteryValues.length) : 0;

  return (
    <div className="page-enter">
      <header className="page-header">
        <div><p className="eyebrow">Your campaign</p><h1>Systems Adventure</h1><p>Follow the data, test your judgment, and make the whole platform click.</p></div>
        <div className="streak-chip"><Lightning size={19} weight="fill" /><span><strong>{reviews}</strong> reviews ready</span></div>
      </header>

      <section className="dashboard-grid">
        <article className="continue-card">
          <div className="continue-card__copy">
            <span className="tag tag--amber">Recommended next</span>
            <p className="eyebrow">Chapter {recommended?.chapter ?? 1}</p>
            <h2>{recommended?.title ?? "Campaign complete"}</h2>
            <p>{recommended?.summary || "Revisit your weakest evidence boundary in Daily Review."}</p>
            {recommended && <button className="button button--dark" onClick={() => onMission(recommended)}>Begin mission <ArrowRight size={18} /></button>}
          </div>
          <div className="system-orbit" aria-hidden="true"><Compass size={52} weight="duotone" /><span>Trace</span><span>Decide</span><span>Prove</span></div>
        </article>
        <article className="mastery-card">
          <div className="mastery-ring" style={{ "--progress": `${mastery * 3.6}deg` } as React.CSSProperties}><strong>{mastery}%</strong><span>mastery</span></div>
          <div><p className="eyebrow">Operator readiness</p><h3>{mastery < 50 ? "Building the mental model" : "Connecting the boundaries"}</h3><p>{completed.size} of {allMissions.length} missions complete</p></div>
        </article>
      </section>

      <section className="campaign-section" aria-labelledby="campaign-heading">
        <div className="section-title"><div><p className="eyebrow">Seven worlds</p><h2 id="campaign-heading">The complete system map</h2></div><Path size={30} weight="duotone" /></div>
        <div className="world-path">
          {data.worlds.map((world, worldIndex) => {
            const worldComplete = world.missions.filter((mission) => completed.has(mission.id)).length;
            return (
              <article className="world-card" key={world.id} style={{ "--delay": worldIndex } as React.CSSProperties}>
                <div className="world-card__number">{worldNumbers[world.id] ?? String(worldIndex + 1).padStart(2, "0")}</div>
                <div className="world-card__header"><div><h3>{world.title}</h3><p>{world.description}</p></div><span>{worldComplete}/{world.missions.length}</span></div>
                <div className="mission-list">
                  {world.missions.map((mission) => (
                    <button className="mission-row" key={mission.id} onClick={() => onMission(mission)}>
                      {completed.has(mission.id) ? <CheckCircle size={20} weight="fill" /> : <span className="mission-dot" />}
                      <span><small>Chapter {mission.chapter}</small>{mission.title}</span>
                      <ArrowRight size={17} />
                    </button>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {completed.size === allMissions.length && <div className="completion-banner"><Trophy size={28} weight="duotone" /> Campaign complete—keep mastery strong in Daily Review.</div>}
    </div>
  );
}
