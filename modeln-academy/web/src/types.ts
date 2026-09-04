export type Beat = {
  type: "brief" | "explore" | "decide" | "recall" | "debrief";
  title: string;
  question_ids?: string[];
};

export type Mission = {
  id: string;
  title: string;
  chapter: number;
  summary: string;
  citation_id: string;
  beats: Beat[];
};

export type World = {
  id: string;
  title: string;
  description: string;
  missions: Mission[];
};

export type Dashboard = {
  worlds: World[];
  recommended_mission_id: string | null;
  mastery: Record<string, number>;
  completed_missions: string[];
};

export type Question = {
  id: string;
  type: string;
  prompt: string;
  options?: string[];
  items?: string[];
  mastery_skill: string;
  citation_id: string;
};

export type Reference = {
  id?: string;
  title: string;
  content: string;
  evidence_class: string;
};

export type Attempt = {
  attempt_id: string;
  current_beat: number;
};

export type AnswerResult = {
  correct: boolean;
  score: number;
  new_mastery: number;
  explanation: string;
  citation_id: string;
};

export type Review = { question_id: string; due_at: string; repetitions: number };
export type SimulationSummary = { id: string; title: string };
export type SimulationChoice = { id: string; label: string; citation_id?: string };
export type SimulationState = {
  run_id: string;
  state_id: string;
  prompt: string;
  choices: SimulationChoice[];
  terminal: boolean;
  score: number;
  score_delta?: number;
};

export type SearchResult = {
  id: string;
  title: string;
  text: string;
  kind: string;
  reference_id: string;
  score: number;
};
