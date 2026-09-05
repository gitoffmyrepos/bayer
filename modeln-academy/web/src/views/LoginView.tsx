import { ArrowRight, Compass, ShieldCheck } from "@phosphor-icons/react";
import { FormEvent, useState } from "react";

import { ThemeSelector } from "../components/ThemeSelector";
import type { Theme } from "../theme";

export function LoginView({
  onLogin,
  theme,
  onThemeChange,
}: {
  onLogin: (username: string, password: string) => Promise<void>;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onLogin(username, password);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-story">
        <div className="brand-mark"><Compass size={27} weight="duotone" /></div>
        <p className="eyebrow">ModelN Systems Adventure</p>
        <h1>Trace the system.<br />Build real operator instinct.</h1>
        <p className="login-lead">Forty chapters become short missions, source-backed decisions, and incident drills you can actually remember.</p>
        <div className="route-preview" aria-hidden="true">
          <span>Source</span><i /><span>Middleware</span><i /><span>Model N</span><i /><span>Evidence</span>
        </div>
      </section>
      <section className="login-card" aria-labelledby="login-heading">
        <ThemeSelector theme={theme} onChange={onThemeChange} className="login-theme" />
        <ShieldCheck size={30} weight="duotone" />
        <p className="eyebrow">Private homelab access</p>
        <h2 id="login-heading">Enter the academy</h2>
        <p>Your progress follows you securely across devices on your internal network.</p>
        <form onSubmit={submit}>
          <label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button--primary button--wide" disabled={!username || !password || busy}>
            {busy ? "Opening…" : "Start learning"}<ArrowRight size={18} />
          </button>
        </form>
      </section>
    </main>
  );
}
