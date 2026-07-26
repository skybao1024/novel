"""Canon propositions, scoped assertions, provenance, and append-only changes."""

from novel_core.canon.assertions import Assertion, AssertionScope, AssertionStance
from novel_core.canon.changes import (
    CanonChangeSet,
    ChangeSetOperation,
    ChangeSetOperationKind,
)
from novel_core.canon.ledger import (
    EMPTY_CANON_REVISION,
    CanonLedgerEntry,
    CanonLedgerSnapshot,
    ChangeSetLedgerRecord,
    DocumentLedgerRecord,
    EntityAliasLedgerRecord,
    EntityLedgerRecord,
    EventEdgeLedgerRecord,
    EventLedgerRecord,
    LedgerReplayError,
    SceneLedgerRecord,
    SourceRefLedgerRecord,
    next_canon_revision,
    replay_ledger,
)
from novel_core.canon.propositions import ObjectKind, Proposition, Qualifier
from novel_core.canon.queries import (
    CHARACTER_GOAL_PREDICATE,
    CHARACTER_LOCATION_PREDICATE,
    CharacterState,
    CharacterStatePhase,
    EventChain,
    EventChainDirection,
    QueryWarning,
    SourcedAssertion,
)
from novel_core.canon.sources import SourceRef

__all__ = [
    "Assertion",
    "AssertionScope",
    "AssertionStance",
    "CHARACTER_GOAL_PREDICATE",
    "CHARACTER_LOCATION_PREDICATE",
    "CanonLedgerEntry",
    "CanonLedgerSnapshot",
    "CanonChangeSet",
    "ChangeSetLedgerRecord",
    "ChangeSetOperation",
    "ChangeSetOperationKind",
    "CharacterState",
    "CharacterStatePhase",
    "DocumentLedgerRecord",
    "EMPTY_CANON_REVISION",
    "EntityAliasLedgerRecord",
    "EntityLedgerRecord",
    "EventEdgeLedgerRecord",
    "EventLedgerRecord",
    "EventChain",
    "EventChainDirection",
    "LedgerReplayError",
    "ObjectKind",
    "Proposition",
    "Qualifier",
    "QueryWarning",
    "SceneLedgerRecord",
    "SourceRef",
    "SourceRefLedgerRecord",
    "SourcedAssertion",
    "next_canon_revision",
    "replay_ledger",
]
