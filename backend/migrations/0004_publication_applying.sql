ALTER TABLE publications RENAME TO publications_before_applying;

CREATE TABLE publications (
    publication_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    writing_session_id TEXT NOT NULL REFERENCES writing_sessions(writing_session_id),
    draft_revision TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'prepared',
            'approved',
            'applying',
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

INSERT INTO publications(
    publication_id,
    project_id,
    writing_session_id,
    draft_revision,
    status,
    approval_digest,
    payload_json
)
SELECT
    publication_id,
    project_id,
    writing_session_id,
    draft_revision,
    status,
    approval_digest,
    payload_json
FROM publications_before_applying;

DROP TABLE publications_before_applying;

CREATE INDEX publications_by_project_status
    ON publications(project_id, status, publication_id);
