CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE project_metadata (
    project_id TEXT PRIMARY KEY,
    project_format_version INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json))
) STRICT;

CREATE TABLE projection_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    canon_revision TEXT NOT NULL,
    last_ledger_sequence INTEGER NOT NULL CHECK (last_ledger_sequence >= 0),
    navigation_revision TEXT NOT NULL
) STRICT;

CREATE TABLE ledger_entries (
    ledger_sequence INTEGER PRIMARY KEY CHECK (ledger_sequence >= 1),
    ledger_entry_id TEXT NOT NULL UNIQUE,
    base_revision TEXT NOT NULL,
    result_revision TEXT NOT NULL UNIQUE,
    approved_at TEXT NOT NULL,
    source_chapter_id TEXT,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
    created_revision TEXT NOT NULL,
    retired_revision TEXT,
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    document_kind TEXT NOT NULL CHECK (
        document_kind IN ('manuscript', 'manual', 'structure')
    ),
    revision TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE entity_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    alias_text TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    used_by_entity_id TEXT REFERENCES entities(entity_id),
    valid_from_json TEXT CHECK (valid_from_json IS NULL OR json_valid(valid_from_json)),
    valid_to_json TEXT CHECK (valid_to_json IS NULL OR json_valid(valid_to_json)),
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE chapters (
    chapter_id TEXT PRIMARY KEY,
    volume_id TEXT,
    chapter_number INTEGER NOT NULL UNIQUE CHECK (chapter_number >= 1),
    title TEXT NOT NULL,
    narrative_order INTEGER NOT NULL CHECK (narrative_order >= 1),
    timeline_id TEXT NOT NULL,
    story_time_kind TEXT NOT NULL,
    story_ordinal_start INTEGER,
    story_ordinal_end INTEGER,
    story_text_start TEXT,
    story_text_end TEXT,
    story_time_json TEXT NOT NULL CHECK (json_valid(story_time_json)),
    pov_entity_id TEXT REFERENCES entities(entity_id),
    location_entity_id TEXT REFERENCES entities(entity_id),
    status TEXT NOT NULL CHECK (
        status IN ('planned', 'drafting', 'candidate', 'approved', 'superseded')
    ),
    source_document_id TEXT NOT NULL REFERENCES documents(document_id),
    revision TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE source_refs (
    source_ref_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    document_revision TEXT NOT NULL,
    fragment_ordinal INTEGER NOT NULL CHECK (fragment_ordinal >= 1),
    quote_hash TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE propositions (
    proposition_id TEXT PRIMARY KEY,
    subject_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    predicate TEXT NOT NULL,
    object_kind TEXT NOT NULL CHECK (object_kind IN ('entity', 'value')),
    object_entity_id TEXT REFERENCES entities(entity_id),
    object_value_json TEXT CHECK (
        object_value_json IS NULL OR json_valid(object_value_json)
    ),
    qualifiers_json TEXT NOT NULL CHECK (json_valid(qualifiers_json)),
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    CHECK (
        (object_kind = 'entity' AND object_entity_id IS NOT NULL AND object_value_json IS NULL)
        OR
        (object_kind = 'value' AND object_entity_id IS NULL AND object_value_json IS NOT NULL)
    )
) STRICT;

CREATE TABLE canon_changesets (
    change_set_id TEXT PRIMARY KEY,
    base_revision TEXT NOT NULL,
    source_chapter_id TEXT REFERENCES chapters(chapter_id),
    approved_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL UNIQUE REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE assertions (
    assertion_id TEXT PRIMARY KEY,
    proposition_id TEXT NOT NULL REFERENCES propositions(proposition_id),
    scope TEXT NOT NULL CHECK (
        scope IN ('objective', 'character', 'reader', 'narrator')
    ),
    holder_entity_id TEXT REFERENCES entities(entity_id),
    stance TEXT NOT NULL CHECK (
        stance IN ('true', 'false', 'unknown', 'suspected', 'claimed', 'disbelieved')
    ),
    certainty REAL NOT NULL CHECK (certainty >= 0.0 AND certainty <= 1.0),
    valid_from_timeline_id TEXT NOT NULL,
    valid_from_kind TEXT NOT NULL,
    valid_from_ordinal INTEGER,
    valid_from_json TEXT NOT NULL CHECK (json_valid(valid_from_json)),
    valid_to_timeline_id TEXT,
    valid_to_kind TEXT,
    valid_to_ordinal INTEGER,
    valid_to_json TEXT CHECK (valid_to_json IS NULL OR json_valid(valid_to_json)),
    source_ref_id TEXT NOT NULL REFERENCES source_refs(source_ref_id),
    change_set_id TEXT NOT NULL REFERENCES canon_changesets(change_set_id),
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    CHECK (
        (scope = 'character' AND holder_entity_id IS NOT NULL)
        OR
        (scope IN ('objective', 'reader') AND holder_entity_id IS NULL)
        OR
        scope = 'narrator'
    )
) STRICT;

CREATE TABLE canon_change_operations (
    operation_id TEXT PRIMARY KEY,
    change_set_id TEXT NOT NULL REFERENCES canon_changesets(change_set_id),
    operation_order INTEGER NOT NULL CHECK (operation_order >= 1),
    op TEXT NOT NULL CHECK (op IN ('assert', 'retract', 'supersede', 'correct')),
    target_assertion_id TEXT REFERENCES assertions(assertion_id),
    new_assertion_id TEXT REFERENCES assertions(assertion_id),
    new_proposition_id TEXT REFERENCES propositions(proposition_id),
    reason TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    UNIQUE (change_set_id, operation_order)
) STRICT;

CREATE UNIQUE INDEX one_invalidation_per_assertion
    ON canon_change_operations(target_assertion_id)
    WHERE target_assertion_id IS NOT NULL;

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    story_time_kind TEXT NOT NULL,
    story_ordinal_start INTEGER,
    story_ordinal_end INTEGER,
    story_text_start TEXT,
    story_text_end TEXT,
    story_time_json TEXT NOT NULL CHECK (json_valid(story_time_json)),
    narrative_order INTEGER NOT NULL CHECK (narrative_order >= 1),
    source_chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    summary TEXT NOT NULL,
    canon_status TEXT NOT NULL CHECK (
        canon_status IN ('candidate', 'approved', 'superseded')
    ),
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE event_participants (
    event_id TEXT NOT NULL REFERENCES events(event_id),
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    participant_order INTEGER NOT NULL CHECK (participant_order >= 1),
    PRIMARY KEY (event_id, entity_id)
) STRICT;

CREATE TABLE event_locations (
    event_id TEXT NOT NULL REFERENCES events(event_id),
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    location_order INTEGER NOT NULL CHECK (location_order >= 1),
    PRIMARY KEY (event_id, entity_id)
) STRICT;

CREATE TABLE event_source_refs (
    event_id TEXT NOT NULL REFERENCES events(event_id),
    source_ref_id TEXT NOT NULL REFERENCES source_refs(source_ref_id),
    source_order INTEGER NOT NULL CHECK (source_order >= 1),
    PRIMARY KEY (event_id, source_ref_id)
) STRICT;

CREATE TABLE event_edges (
    event_edge_id TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL REFERENCES events(event_id),
    target_event_id TEXT NOT NULL REFERENCES events(event_id),
    edge_type TEXT NOT NULL CHECK (
        edge_type IN (
            'causes',
            'enables',
            'prevents',
            'reveals',
            'foreshadows',
            'pays_off',
            'contradicts'
        )
    ),
    source_ref_id TEXT REFERENCES source_refs(source_ref_id),
    schema_version TEXT NOT NULL,
    ledger_sequence INTEGER NOT NULL REFERENCES ledger_entries(ledger_sequence),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    CHECK (source_event_id <> target_event_id)
) STRICT;

CREATE TABLE volumes (
    volume_id TEXT PRIMARY KEY,
    volume_number INTEGER NOT NULL UNIQUE CHECK (volume_number >= 1),
    title TEXT NOT NULL CHECK (length(title) > 0),
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE TABLE volume_chapters (
    volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
    chapter_id TEXT NOT NULL UNIQUE REFERENCES chapters(chapter_id),
    chapter_number_in_volume INTEGER NOT NULL CHECK (chapter_number_in_volume >= 1),
    PRIMARY KEY (volume_id, chapter_number_in_volume),
    UNIQUE (volume_id, chapter_id)
) STRICT;

CREATE TABLE navigation_summaries (
    rowid INTEGER PRIMARY KEY,
    summary_key TEXT NOT NULL UNIQUE,
    summary_kind TEXT NOT NULL CHECK (summary_kind IN ('volume', 'chapter')),
    volume_id TEXT NOT NULL REFERENCES volumes(volume_id),
    chapter_id TEXT REFERENCES chapters(chapter_id),
    source_revision TEXT,
    max_narrative_order INTEGER NOT NULL CHECK (max_narrative_order >= 1),
    summary TEXT NOT NULL CHECK (length(summary) > 0),
    is_stale INTEGER NOT NULL CHECK (is_stale IN (0, 1)),
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    CHECK (
        (summary_kind = 'volume' AND chapter_id IS NULL AND source_revision IS NULL)
        OR
        (summary_kind = 'chapter' AND chapter_id IS NOT NULL AND source_revision IS NOT NULL)
    )
) STRICT;

CREATE TABLE navigation_summary_entities (
    summary_key TEXT NOT NULL REFERENCES navigation_summaries(summary_key),
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    entity_order INTEGER NOT NULL CHECK (entity_order >= 1),
    PRIMARY KEY (summary_key, entity_id),
    UNIQUE (summary_key, entity_order)
) STRICT;

CREATE VIRTUAL TABLE navigation_summaries_fts USING fts5(
    summary,
    content='navigation_summaries',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE INDEX aliases_by_text ON entity_aliases(alias_text);
CREATE INDEX assertions_by_proposition_scope_holder
    ON assertions(proposition_id, scope, holder_entity_id);
CREATE INDEX assertions_by_ordinal
    ON assertions(valid_from_timeline_id, valid_from_kind, valid_from_ordinal);
CREATE INDEX events_by_narrative_order ON events(narrative_order);
CREATE INDEX events_by_story_ordinal
    ON events(timeline_id, story_time_kind, story_ordinal_start);
CREATE INDEX event_participants_by_entity
    ON event_participants(entity_id, event_id);
CREATE INDEX event_locations_by_entity
    ON event_locations(entity_id, event_id);
CREATE INDEX event_edges_by_source ON event_edges(source_event_id);
CREATE INDEX event_edges_by_target ON event_edges(target_event_id);
CREATE INDEX volumes_by_number ON volumes(volume_number, volume_id);
CREATE INDEX volume_chapters_by_chapter
    ON volume_chapters(chapter_id, volume_id, chapter_number_in_volume);
CREATE INDEX navigation_summaries_by_kind_order
    ON navigation_summaries(summary_kind, max_narrative_order, summary_key);
CREATE INDEX navigation_summaries_by_volume
    ON navigation_summaries(volume_id, summary_kind, chapter_id);
CREATE INDEX navigation_summary_entities_by_entity
    ON navigation_summary_entities(entity_id, summary_key);
