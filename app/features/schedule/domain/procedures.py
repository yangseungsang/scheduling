"""TestProcedure domain types shared by scheduling and execution features."""

from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class TestItem:
    """Smallest schedulable and executable item inside a procedure."""
    __test__ = False
    id: str
    name: str = ''
    estimated_minutes: int = 0
    total_count: int = 0
    owner_names: Tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data):
        """Normalize current and legacy external field names."""
        return cls(
            id=str(data.get('id', '')),
            name=data.get('name', ''),
            estimated_minutes=int(data.get('estimated_minutes') or 0),
            total_count=int(data.get('total_count') or data.get('pf_num') or 0),
            owner_names=tuple(data.get('owner_names') or data.get('owners') or []),
        )

    def to_dict(self):
        """Serialize non-default item fields for the plan document."""
        result = {
            'id': self.id,
        }
        if self.name:
            result['name'] = self.name
        if self.estimated_minutes:
            result['estimated_minutes'] = self.estimated_minutes
        if self.total_count:
            result['total_count'] = self.total_count
        if self.owner_names:
            result['owner_names'] = list(self.owner_names)
        return result


@dataclass(frozen=True)
class TestProcedure:
    """A document/test-round aggregate containing related test items."""
    __test__ = False
    id: str
    document_id: Optional[str] = None
    document_name: str = ''
    test_round: Optional[int] = None
    test_items: Tuple[TestItem, ...] = ()
    estimated_minutes: int = 0
    assignee_names: Tuple[str, ...] = ()
    memo: str = ''
    state: str = 'active'
    kind: str = 'test'

    @classmethod
    def from_dict(cls, data):
        """Build a procedure and derive defaults from its test items."""
        document_id = data.get('document_id')
        test_items = tuple(
            TestItem.from_dict(item) for item in data.get('test_items', [])
        )
        return cls(
            id=data['id'],
            document_id=None if document_id in (None, '') else str(document_id),
            document_name=data.get('document_name', ''),
            test_round=data.get('test_round'),
            test_items=test_items,
            estimated_minutes=int(
                data.get('estimated_minutes')
                if data.get('estimated_minutes') is not None
                else sum(item.estimated_minutes for item in test_items)
            ),
            assignee_names=tuple(data.get('assignee_names', [])),
            memo=data.get('memo', ''),
            state=data.get('state', 'active'),
            kind='simple' if not test_items else 'test',
        )

    def to_dict(self):
        """Serialize a procedure while omitting reconstructable defaults."""
        result = {
            'id': self.id,
        }
        if self.document_id is not None:
            result['document_id'] = self.document_id
        if self.document_name:
            result['document_name'] = self.document_name
        if self.test_round is not None:
            result['test_round'] = self.test_round
        if self.test_items:
            result['test_items'] = [item.to_dict() for item in self.test_items]
        test_item_minutes = sum(
            item.estimated_minutes for item in self.test_items
        )
        if self.estimated_minutes and self.estimated_minutes != test_item_minutes:
            result['estimated_minutes'] = self.estimated_minutes
        if self.assignee_names:
            result['assignee_names'] = list(self.assignee_names)
        if self.memo:
            result['memo'] = self.memo
        if self.state != 'active':
            result['state'] = self.state
        return result
