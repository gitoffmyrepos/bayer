import { BookOpen, MagnifyingGlass, Sparkle } from "@phosphor-icons/react";
import { FormEvent, useState } from "react";

import { api } from "../api";
import type { SearchResult } from "../types";

export function AtlasView() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [coach, setCoach] = useState<{ grounded: boolean; answer: string; citations: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);

  async function search(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setBusy(true);
    try {
      const [matches, digest] = await Promise.all([api.search(query), api.coach(query)]);
      setResults(matches);
      setCoach(digest);
      setSearched(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="atlas-page page-enter">
      <header className="page-header"><div><p className="eyebrow">Evidence atlas</p><h1>Find the real boundary</h1><p>Search FGIs, source systems, workflows, jobs, tables, and the cited guide.</p></div><BookOpen size={38} weight="duotone" /></header>
      <form className="search-bar" onSubmit={search}>
        <MagnifyingGlass size={22} />
        <input type="search" role="searchbox" aria-label="Search the evidence atlas" placeholder="Try FGI 205, RODB, control table…" value={query} onChange={(event) => setQuery(event.target.value)} />
        <button className="button button--primary" disabled={busy || query.trim().length < 2}>{busy ? "Searching…" : "Search"}</button>
      </form>
      {!searched && <div className="atlas-intro"><p className="eyebrow">Source-backed result</p><h2>Ask a precise operator question</h2><p>The atlas keeps configured facts, verified behavior, environment evidence, and hypotheses visibly separate.</p><div className="suggestion-row">{["FGI 301", "current load", "Glue retry", "DynamoDB control"].map((item) => <button key={item} onClick={() => setQuery(item)}>{item}</button>)}</div></div>}
      {coach && <section className={coach.grounded ? "coach-card" : "coach-card coach-card--empty"}><div><Sparkle size={22} weight="duotone" /><strong>Evidence coach</strong></div><p>{coach.answer}</p>{coach.citations.length > 0 && <small>Cited from {coach.citations.length} course reference{coach.citations.length === 1 ? "" : "s"}.</small>}</section>}
      <div className="search-results">
        {results.map((result) => <article className="search-result" key={result.id}><div><span className="tag">{result.kind.replaceAll("_", " ")}</span><span className="source-label">Source-backed result</span></div><h2>{result.title}</h2><p>{result.text}</p><small>Reference: {result.reference_id}</small></article>)}
        {searched && !results.length && <div className="state-panel"><p>No matching evidence. Try an exact FGI, job, table, or workflow name.</p></div>}
      </div>
    </div>
  );
}
