CREATE TABLE chapter_traces (
    chapter_id TEXT PRIMARY KEY REFERENCES chapters(chapter_id),
    chapter_trace_id TEXT NOT NULL UNIQUE,
    volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
    source_document_id TEXT NOT NULL REFERENCES documents(document_id),
    source_revision TEXT NOT NULL,
    is_stale INTEGER NOT NULL CHECK (is_stale IN (0, 1)),
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE chapter_entity_occurrences (
    chapter_id TEXT NOT NULL REFERENCES chapter_traces(chapter_id),
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    occurrence_order INTEGER NOT NULL CHECK (occurrence_order >= 1),
    presence_kind TEXT NOT NULL CHECK (
        presence_kind IN ('present', 'mentioned', 'recalled', 'offstage')
    ),
    prominence TEXT NOT NULL CHECK (
        prominence IN ('focus', 'supporting', 'cameo', 'background')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    PRIMARY KEY (chapter_id, entity_id),
    UNIQUE (chapter_id, occurrence_order)
) STRICT;

CREATE INDEX chapter_entity_occurrences_by_entity
    ON chapter_entity_occurrences(entity_id, chapter_id);
