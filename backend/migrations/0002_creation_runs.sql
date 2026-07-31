ALTER TABLE projection_state ADD COLUMN run_revision TEXT NOT NULL DEFAULT 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';

CREATE TABLE bootstrap_runs (
    bootstrap_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('drafting', 'prepared', 'approved', 'applied')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE intent_revisions (
    intent_revision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('prepared', 'approved', 'applied')),
    base_intent_revision TEXT NOT NULL,
    candidate_revision TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE writing_sessions (
    writing_session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    target_chapter_id TEXT NOT NULL,
    target_volume_id TEXT NOT NULL,
    target_narrative_order INTEGER NOT NULL,
    base_canon_revision TEXT NOT NULL,
    base_intent_revision TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE draft_revisions (
    writing_session_id TEXT NOT NULL REFERENCES writing_sessions(writing_session_id),
    draft_revision TEXT NOT NULL,
    parent_revision TEXT,
    content_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    PRIMARY KEY (writing_session_id, draft_revision)
) STRICT;

CREATE TABLE retrieved_sources (
    retrieved_source_id TEXT PRIMARY KEY,
    writing_session_id TEXT NOT NULL REFERENCES writing_sessions(writing_session_id),
    retrieval_kind TEXT NOT NULL,
    chapter_id TEXT,
    document_id TEXT,
    document_revision TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY,
    writing_session_id TEXT NOT NULL REFERENCES writing_sessions(writing_session_id),
    draft_revision TEXT NOT NULL,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('revise', 'ready')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    FOREIGN KEY (writing_session_id, draft_revision)
        REFERENCES draft_revisions(writing_session_id, draft_revision)
) STRICT;

CREATE TABLE publications (
    publication_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    writing_session_id TEXT NOT NULL REFERENCES writing_sessions(writing_session_id),
    draft_revision TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'prepared',
            'approved',
            'manuscript_installed',
            'navigation_installed',
            'intent_installed',
            'ledger_appended',
            'projection_rebuilt',
            'completed'
        )
    ),
    approval_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    FOREIGN KEY (writing_session_id, draft_revision)
        REFERENCES draft_revisions(writing_session_id, draft_revision)
) STRICT;

CREATE INDEX writing_sessions_by_project_status
    ON writing_sessions(project_id, status, writing_session_id);
CREATE INDEX drafts_by_session ON draft_revisions(writing_session_id, draft_revision);
CREATE INDEX reviews_by_session_draft
    ON reviews(writing_session_id, draft_revision, review_id);
CREATE INDEX publications_by_project_status
    ON publications(project_id, status, publication_id);
CREATE INDEX retrieved_sources_by_session
    ON retrieved_sources(writing_session_id, retrieved_source_id);
