import { BookOpen, Compass, DoorOpen, Flask, House, Repeat } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";
import { ErrorState, LoadingState } from "./components/LoadingState";
import type { Dashboard, Review, SimulationSummary } from "./types";
import { AtlasView } from "./views/AtlasView";
import { DashboardView } from "./views/DashboardView";
import { LoginView } from "./views/LoginView";
import { MissionView } from "./views/MissionView";
import { ReviewView } from "./views/ReviewView";
import { SimulationView } from "./views/SimulationView";

type View = "campaign" | "review" | "atlas" | "incident";

export default function App() {
  const [auth, setAuth] = useState<"loading" | "anonymous" | "authenticated">("loading");
  const [name, setName] = useState("");
  const [view, setView] = useState<View>("campaign");
  const [missionId, setMissionId] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [simulations, setSimulations] = useState<SimulationSummary[]>([]);
  const [error, setError] = useState("");

  const loadAcademy = useCallback(async () => {
    try {
      const identity = await api.me();
      const [campaign, reviewQueue, cases] = await Promise.all([api.dashboard(), api.reviews(), api.simulations()]);
      setName(identity.display_name);
      setDashboard(campaign);
      setReviews(reviewQueue);
      setSimulations(cases);
      setAuth("authenticated");
      setError("");
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setAuth("anonymous");
      else { setError(reason instanceof Error ? reason.message : "The academy is unavailable."); setAuth("anonymous"); }
    }
  }, []);

  useEffect(() => { void loadAcademy(); }, [loadAcademy]);

  async function login(username: string, password: string) {
    await api.login(username, password);
    await loadAcademy();
  }

  async function logout() {
    await api.logout();
    setAuth("anonymous");
    setDashboard(null);
    setMissionId(null);
  }

  if (auth === "loading") return <LoadingState />;
  if (auth === "anonymous") return <LoginView onLogin={login} />;
  if (error && !dashboard) return <ErrorState message={error} retry={() => void loadAcademy()} />;
  if (missionId) return <MissionView missionId={missionId} onClose={() => setMissionId(null)} onComplete={() => void loadAcademy()} />;
  if (!dashboard) return <LoadingState />;

  const navItems = [
    { id: "campaign" as const, label: "Campaign", icon: House },
    { id: "review" as const, label: "Daily review", icon: Repeat },
    { id: "atlas" as const, label: "Evidence atlas", icon: BookOpen },
    { id: "incident" as const, label: "Incident lab", icon: Flask },
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span><Compass size={23} weight="duotone" /></span><div><strong>ModelN</strong><small>Systems Adventure</small></div></div>
        <nav aria-label="Academy sections">
          {navItems.map((item) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? "nav-button nav-button--active" : "nav-button"} onClick={() => setView(item.id)}><Icon size={21} weight={view === item.id ? "fill" : "regular"} /><span>{item.label}</span>{item.id === "review" && reviews.length > 0 && <b>{reviews.length}</b>}</button>; })}
        </nav>
        <div className="sidebar-profile"><span>{name.slice(0, 1).toUpperCase()}</span><div><strong>{name}</strong><small>Private learner</small></div><button aria-label="Sign out" onClick={() => void logout()}><DoorOpen size={19} /></button></div>
      </aside>
      <main className="app-content">
        {view === "campaign" && <DashboardView data={dashboard} reviews={reviews.length} onMission={(mission) => setMissionId(mission.id)} />}
        {view === "review" && <ReviewView initialReviews={reviews} />}
        {view === "atlas" && <AtlasView />}
        {view === "incident" && <SimulationView simulations={simulations} />}
      </main>
      <nav className="mobile-nav" aria-label="Academy sections">
        {navItems.map((item) => { const Icon = item.icon; return <button key={item.id} aria-label={item.label} className={view === item.id ? "mobile-nav__active" : ""} onClick={() => setView(item.id)}><Icon size={22} weight={view === item.id ? "fill" : "regular"} /><small>{item.label.split(" ")[0]}</small></button>; })}
      </nav>
    </div>
  );
}
