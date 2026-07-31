"""Domain-aware queries over a replaceable projection adapter."""

from __future__ import annotations

from uuid import UUID

from novel_application.models import AssertionHistoryItem, EventOrder
from novel_application.ports import ProjectionQueryPort
from novel_core import (
    CHARACTER_GOAL_PREDICATE,
    CHARACTER_LOCATION_PREDICATE,
    Assertion,
    AssertionScope,
    AssertionStance,
    ChangeSetOperationKind,
    Chapter,
    CharacterState,
    CharacterStatePhase,
    Document,
    Entity,
    Event,
    EventChain,
    EventChainDirection,
    EventEdge,
    Proposition,
    QueryWarning,
    SourcedAssertion,
    SourceRef,
    StoryTimeKind,
)


class CanonQueryService:
    """Expose query behavior while keeping correction semantics out of SQL."""

    def __init__(self, projection: ProjectionQueryPort) -> None:
        self._projection = projection

    def get_entity(self, entity_id: UUID) -> Entity | None:
        return self._projection.get_entity(entity_id)

    def list_entities(self) -> tuple[Entity, ...]:
        return self._projection.list_entities()

    def find_entities_by_alias(self, alias_text: str) -> tuple[Entity, ...]:
        return self._projection.find_entities_by_alias(alias_text)

    def get_document(self, document_id: UUID) -> Document | None:
        return self._projection.get_document(document_id)

    def get_chapter(self, chapter_id: UUID) -> Chapter | None:
        return self._projection.get_chapter(chapter_id)

    def get_event(self, event_id: UUID) -> Event | None:
        return self._projection.get_event(event_id)

    def get_source_ref(self, source_ref_id: UUID) -> SourceRef | None:
        return self._projection.get_source_ref(source_ref_id)

    def get_proposition(self, proposition_id: UUID) -> Proposition | None:
        return self._projection.get_proposition(proposition_id)

    def assertion_history(
        self,
        *,
        proposition_id: UUID | None = None,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        scope: AssertionScope | None = None,
        holder_entity_id: UUID | None = None,
    ) -> tuple[AssertionHistoryItem, ...]:
        return self._projection.assertion_history(
            proposition_id=proposition_id,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            scope=scope,
            holder_entity_id=holder_entity_id,
        )

    def effective_assertions(
        self,
        *,
        timeline_id: str,
        story_ordinal: int,
        proposition_id: UUID | None = None,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        scope: AssertionScope | None = None,
        holder_entity_id: UUID | None = None,
    ) -> tuple[Assertion, ...]:
        history = self.assertion_history(
            proposition_id=proposition_id,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            scope=scope,
            holder_entity_id=holder_entity_id,
        )
        return tuple(
            item.assertion
            for item in history
            if _assertion_is_effective_at(
                item,
                timeline_id=timeline_id,
                story_ordinal=story_ordinal,
            )
        )

    def list_events(
        self,
        *,
        participant_entity_id: UUID | None = None,
        location_entity_id: UUID | None = None,
        source_chapter_id: UUID | None = None,
        order: EventOrder = EventOrder.NARRATIVE,
    ) -> tuple[Event, ...]:
        return self._projection.list_events(
            participant_entity_id=participant_entity_id,
            location_entity_id=location_entity_id,
            source_chapter_id=source_chapter_id,
            order=order,
        )

    def event_edges(
        self,
        event_id: UUID,
        *,
        direction: str,
    ) -> tuple[EventEdge, ...]:
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("direction must be 'incoming' or 'outgoing'")
        return self._projection.event_edges(event_id, direction=direction)

    def source_refs_for_event(self, event_id: UUID) -> tuple[SourceRef, ...]:
        return self._projection.source_refs_for_event(event_id)

    def source_refs_for_chapter(self, chapter_id: UUID) -> tuple[SourceRef, ...]:
        return self._projection.source_refs_for_chapter(chapter_id)

    def character_state(
        self,
        character_id: UUID,
        *,
        at_chapter_id: UUID,
        phase: CharacterStatePhase = CharacterStatePhase.ENTRY,
    ) -> CharacterState:
        chapter = self.get_chapter(at_chapter_id)
        if chapter is None:
            raise ValueError(f"chapter does not exist: {at_chapter_id}")
        if self.get_entity(character_id) is None:
            raise ValueError(f"entity does not exist: {character_id}")

        if chapter.story_time.kind is not StoryTimeKind.ORDINAL:
            return CharacterState(
                character_id=character_id,
                target_chapter_id=at_chapter_id,
                phase=phase,
                story_time=chapter.story_time,
                warnings=(
                    QueryWarning(
                        code="indeterminate_time_order",
                        message="character-state reconstruction requires ordinal StoryTime",
                        related_ids=(str(at_chapter_id),),
                    ),
                ),
            )

        story_ordinal = int(chapter.story_time.story_time_start)
        objective = self._sourced_effective_assertions(
            timeline_id=chapter.story_time.timeline_id,
            story_ordinal=story_ordinal,
            subject_entity_id=character_id,
            scope=AssertionScope.OBJECTIVE,
            at_chapter_id=at_chapter_id,
            phase=phase,
        )
        knowledge = self._sourced_effective_assertions(
            timeline_id=chapter.story_time.timeline_id,
            story_ordinal=story_ordinal,
            holder_entity_id=character_id,
            scope=AssertionScope.CHARACTER,
            at_chapter_id=at_chapter_id,
            phase=phase,
        )
        locations = tuple(
            item
            for item in objective
            if item.proposition.predicate == CHARACTER_LOCATION_PREDICATE
            and item.assertion.stance is AssertionStance.TRUE
        )
        goals = tuple(
            item
            for item in objective
            if item.proposition.predicate == CHARACTER_GOAL_PREDICATE
            and item.assertion.stance is AssertionStance.TRUE
        )
        warnings: tuple[QueryWarning, ...] = ()
        location = locations[0] if len(locations) == 1 else None
        if len(locations) > 1:
            warnings = (
                QueryWarning(
                    code="ambiguous_character_location",
                    message="multiple objective locations are effective at this story time",
                    related_ids=tuple(str(item.assertion.assertion_id) for item in locations),
                ),
            )
        return CharacterState(
            character_id=character_id,
            target_chapter_id=at_chapter_id,
            phase=phase,
            story_time=chapter.story_time,
            location=location,
            active_goals=goals,
            knowledge_and_beliefs=knowledge,
            objective_state=objective,
            warnings=warnings,
        )

    def event_chain(
        self,
        event_id: UUID,
        *,
        direction: EventChainDirection = EventChainDirection.BOTH,
        max_depth: int = 3,
    ) -> EventChain:
        root = self.get_event(event_id)
        if root is None:
            raise ValueError(f"event does not exist: {event_id}")
        if not 0 <= max_depth <= 20:
            raise ValueError("max_depth must be between 0 and 20")

        events: dict[UUID, Event] = {event_id: root}
        edges: dict[UUID, EventEdge] = {}
        frontier = (event_id,)
        visited = {event_id}
        for _depth in range(max_depth):
            next_frontier: list[UUID] = []
            for current_id in frontier:
                directions = (
                    ("incoming", "outgoing")
                    if direction is EventChainDirection.BOTH
                    else (direction.value,)
                )
                for edge_direction in directions:
                    for edge in self.event_edges(current_id, direction=edge_direction):
                        edges[edge.event_edge_id] = edge
                        adjacent_id = (
                            edge.source_event_id
                            if edge_direction == "incoming"
                            else edge.target_event_id
                        )
                        if adjacent_id in visited:
                            continue
                        adjacent = self.get_event(adjacent_id)
                        if adjacent is None:
                            continue
                        visited.add(adjacent_id)
                        events[adjacent_id] = adjacent
                        next_frontier.append(adjacent_id)
            if not next_frontier:
                break
            frontier = tuple(sorted(next_frontier, key=str))

        source_refs: dict[UUID, SourceRef] = {}
        for event in events.values():
            for source_ref in self.source_refs_for_event(event.event_id):
                source_refs[source_ref.source_ref_id] = source_ref
        for edge in edges.values():
            if edge.source_ref_id is None:
                continue
            source_ref = self.get_source_ref(edge.source_ref_id)
            if source_ref is not None:
                source_refs[source_ref.source_ref_id] = source_ref
        return EventChain(
            root_event_id=event_id,
            direction=direction,
            max_depth=max_depth,
            events=tuple(events.values()),
            edges=tuple(edges[key] for key in sorted(edges, key=str)),
            source_refs=tuple(source_refs[key] for key in sorted(source_refs, key=str)),
        )

    def _sourced_effective_assertions(
        self,
        *,
        timeline_id: str,
        story_ordinal: int,
        at_chapter_id: UUID,
        phase: CharacterStatePhase,
        subject_entity_id: UUID | None = None,
        scope: AssertionScope | None = None,
        holder_entity_id: UUID | None = None,
    ) -> tuple[SourcedAssertion, ...]:
        history = self.assertion_history(
            subject_entity_id=subject_entity_id,
            scope=scope,
            holder_entity_id=holder_entity_id,
        )
        result: list[SourcedAssertion] = []
        for item in history:
            effective = _assertion_is_effective_at(
                item,
                timeline_id=timeline_id,
                story_ordinal=story_ordinal,
            )
            if (
                not effective
                and phase is CharacterStatePhase.ENTRY
                and _assertion_is_valid_without_invalidation(
                    item.assertion,
                    timeline_id=timeline_id,
                    story_ordinal=story_ordinal,
                )
                and item.invalidating_operation is not None
            ):
                invalidating_source_ref_id = item.invalidating_operation.source_ref_id
                if (
                    invalidating_source_ref_id is None
                    and item.invalidating_operation.assertion is not None
                ):
                    invalidating_source_ref_id = item.invalidating_operation.assertion.source_ref_id
                invalidating_source = (
                    self.get_source_ref(invalidating_source_ref_id)
                    if invalidating_source_ref_id is not None
                    else None
                )
                effective = (
                    invalidating_source is not None
                    and invalidating_source.chapter_id == at_chapter_id
                )
            if not effective:
                continue
            source_ref = self.get_source_ref(item.assertion.source_ref_id)
            proposition = self.get_proposition(item.assertion.proposition_id)
            if source_ref is None or proposition is None:
                continue
            if (
                phase is CharacterStatePhase.ENTRY
                and source_ref.chapter_id == at_chapter_id
                and item.assertion.valid_from.kind is StoryTimeKind.ORDINAL
                and item.assertion.valid_from.story_time_start == story_ordinal
            ):
                continue
            result.append(
                SourcedAssertion(
                    assertion=item.assertion,
                    proposition=proposition,
                    source_ref=source_ref,
                )
            )
        return tuple(result)


def _assertion_is_effective_at(
    item: AssertionHistoryItem,
    *,
    timeline_id: str,
    story_ordinal: int,
) -> bool:
    assertion = item.assertion
    if not _assertion_is_valid_without_invalidation(
        assertion,
        timeline_id=timeline_id,
        story_ordinal=story_ordinal,
    ):
        return False

    invalidation = item.invalidating_operation
    if invalidation is None:
        return True
    if invalidation.op in {
        ChangeSetOperationKind.RETRACT,
        ChangeSetOperationKind.CORRECT,
    }:
        return False

    replacement = invalidation.assertion
    if replacement is None:
        return False
    if (
        replacement.valid_from.timeline_id != timeline_id
        or replacement.valid_from.kind is not StoryTimeKind.ORDINAL
    ):
        return False
    return story_ordinal < replacement.valid_from.story_time_start


def _assertion_is_valid_without_invalidation(
    assertion: Assertion,
    *,
    timeline_id: str,
    story_ordinal: int,
) -> bool:
    if assertion.valid_from.timeline_id != timeline_id:
        return False
    if assertion.valid_from.kind is not StoryTimeKind.ORDINAL:
        return False
    if assertion.valid_from.story_time_start > story_ordinal:
        return False

    if assertion.valid_to is not None:
        if assertion.valid_to.timeline_id != timeline_id:
            return False
        if assertion.valid_to.kind is not StoryTimeKind.ORDINAL:
            return False
        if assertion.valid_to.story_time_start < story_ordinal:
            return False

    return True
