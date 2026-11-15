"""Passage scopes follow corpus order, not numeric node IDs."""

from types import SimpleNamespace

import pytest

from corpus_validate.ai_scope import scope_nodes
from corpus_validate.ai_types import NodeScope, ScopeLevel, UnitRange


def test_passage_uses_slot_order_for_reversed_node_ids() -> None:
    kinds = {1: "word", 2: "word", 3: "book", 4: "paragraph", 5: "paragraph"}
    slots = {3: (1, 2), 4: (2,), 5: (1,)}
    otype = SimpleNamespace(maxNode=5, maxSlot=2, v=kinds.get)
    api = SimpleNamespace(
        F=SimpleNamespace(otype=otype),
        E=SimpleNamespace(oslots=SimpleNamespace(s=slots.__getitem__)),
        T=SimpleNamespace(sectionTypes=("book",)),
        L=SimpleNamespace(
            u=lambda node, otype: (3,),
            d=lambda node, otype=None: (5, 4) if node == 3 else slots[node],
        ),
    )
    scope = NodeScope(
        corpus="mini",
        level=ScopeLevel.passage,
        node_id=5,
        label="passage",
        version="1",
        unit_range=UnitRange(5, 4),
    )
    assert set(scope_nodes(api, scope)) == {1, 2, 4, 5}
    reversed_scope = NodeScope(
        corpus="mini",
        level=ScopeLevel.passage,
        node_id=4,
        label="passage",
        version="1",
        unit_range=UnitRange(4, 5),
    )
    with pytest.raises(ValueError, match="reversed in document order"):
        scope_nodes(api, reversed_scope)
