from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RequestType(str, Enum):
    INQUIRY = "inquiry"
    QUERY = "query"
    COMMAND = "command"


class RequestStatus(str, Enum):
    CREATED = "created"
    CLASSIFYING = "classifying"
    PROCESSING = "processing"
    INPUT_REQUIRED = "input_required"
    AMBIGUOUS = "ambiguous"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVAL_EXPIRED = "approval_expired"
    EXECUTING = "executing"
    EXECUTED = "executed"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"

    @classmethod
    def terminal_statuses(cls) -> frozenset["RequestStatus"]:
        return frozenset({
            cls.EXECUTED, cls.COMPLETED, cls.FAILED,
            cls.ESCALATED, cls.CANCELLED, cls.REJECTED, cls.APPROVAL_EXPIRED,
            cls.SUPERSEDED,
        })

    @property
    def is_terminal(self) -> bool:
        return self in self.terminal_statuses()
