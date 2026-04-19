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

    @classmethod
    def blocking_statuses(cls) -> frozenset["RequestStatus"]:
        """세션 삭제를 막는 상태 — 실제로 처리가 진행 중인 경우만 포함.

        대기 상태(created, input_required, ambiguous, pending_approval)는
        포함하지 않으므로 해당 상태만 남은 세션은 삭제 가능하다.
        """
        return frozenset({
            cls.CLASSIFYING, cls.PROCESSING, cls.APPROVED, cls.EXECUTING,
        })

    @property
    def is_terminal(self) -> bool:
        return self in self.terminal_statuses()

    @property
    def is_blocking(self) -> bool:
        return self in self.blocking_statuses()
