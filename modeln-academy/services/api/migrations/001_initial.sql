BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    csrf_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_sessions_expires_at ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS mission_attempts (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mission_id VARCHAR(160) NOT NULL,
    course_version VARCHAR(64) NOT NULL,
    current_beat INTEGER NOT NULL DEFAULT 0 CHECK (current_beat BETWEEN 0 AND 4),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_open_mission_version UNIQUE (user_id, mission_id, course_version)
);
CREATE INDEX IF NOT EXISTS ix_mission_attempts_user_id ON mission_attempts(user_id);

CREATE TABLE IF NOT EXISTS answer_attempts (
    id VARCHAR(36) PRIMARY KEY,
    submission_id VARCHAR(160) NOT NULL UNIQUE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mission_attempt_id VARCHAR(36) NOT NULL REFERENCES mission_attempts(id) ON DELETE CASCADE,
    question_id VARCHAR(160) NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_answer_attempts_user_id ON answer_attempts(user_id);
CREATE INDEX IF NOT EXISTS ix_answer_attempts_question_id ON answer_attempts(question_id);

CREATE TABLE IF NOT EXISTS mastery (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill VARCHAR(160) NOT NULL,
    score DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_user_skill UNIQUE (user_id, skill)
);
CREATE INDEX IF NOT EXISTS ix_mastery_user_id ON mastery(user_id);

CREATE TABLE IF NOT EXISTS reviews (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id VARCHAR(160) NOT NULL,
    repetitions INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 1,
    ease DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    due_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_user_review_question UNIQUE (user_id, question_id)
);
CREATE INDEX IF NOT EXISTS ix_reviews_user_id ON reviews(user_id);
CREATE INDEX IF NOT EXISTS ix_reviews_due_at ON reviews(due_at);

CREATE TABLE IF NOT EXISTS simulation_runs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scenario_id VARCHAR(160) NOT NULL,
    current_state VARCHAR(160) NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    course_version VARCHAR(64) NOT NULL,
    completed_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_simulation_runs_user_id ON simulation_runs(user_id);

COMMIT;

