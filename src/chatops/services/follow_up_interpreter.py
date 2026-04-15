from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from chatops.services.decision_trace import log_decision_trace

CHOICE_NUMBER_PATTERN = re.compile(r"^(?P<value>\d+)(?:번)?$")
CHOICE_LETTER_PATTERN = re.compile(r"^(?P<value>[a-z])$", re.IGNORECASE)
TRAILING_POLITE_SUFFIX_PATTERN = re.compile(r"(?:야|이야|입니다|이에요|예요)\s*$")


@dataclass(frozen=True)
class FollowUpRewrite:
    kind: str
    message_text: str


class FollowUpInterpreterService:
    def rewrite(
        self,
        *,
        message_text: str,
        previous_request_status: str | None,
        session_context: dict[str, Any] | None,
    ) -> FollowUpRewrite | None:
        if not isinstance(message_text, str) or not message_text.strip():
            return None
        if not isinstance(session_context, dict):
            return None

        task_snapshot = session_context.get("last_task_snapshot")
        if not isinstance(task_snapshot, dict):
            return None
        follow_up_prompt = task_snapshot.get("follow_up_prompt")
        if not isinstance(follow_up_prompt, dict):
            return None

        prompt_kind = str(follow_up_prompt.get("kind") or "")
        if previous_request_status == "ambiguous" and prompt_kind == "choice":
            rewrite = self._rewrite_choice(message_text=message_text, session_context=session_context, prompt=follow_up_prompt)
            self._log_rewrite(
                previous_request_status=previous_request_status,
                prompt_kind=prompt_kind,
                original_message=message_text,
                rewrite=rewrite,
            )
            return rewrite
        if previous_request_status == "input_required" and prompt_kind == "missing_input":
            rewrite = self._rewrite_missing_input(message_text=message_text, prompt=follow_up_prompt)
            self._log_rewrite(
                previous_request_status=previous_request_status,
                prompt_kind=prompt_kind,
                original_message=message_text,
                rewrite=rewrite,
            )
            return rewrite
        return None

    @staticmethod
    def _log_rewrite(
        *,
        previous_request_status: str | None,
        prompt_kind: str,
        original_message: str,
        rewrite: FollowUpRewrite | None,
    ) -> None:
        log_decision_trace(
            stage="follow_up_interpreter",
            decision="rewritten" if rewrite is not None else "skipped",
            reason="follow-up prompt evaluated",
            data={
                "previous_request_status": previous_request_status,
                "prompt_kind": prompt_kind,
                "original_message": original_message,
                "rewrite_kind": rewrite.kind if rewrite is not None else None,
                "rewritten_message": rewrite.message_text if rewrite is not None else None,
            },
        )

    def _rewrite_choice(
        self,
        *,
        message_text: str,
        session_context: dict[str, Any],
        prompt: dict[str, Any],
    ) -> FollowUpRewrite | None:
        options = prompt.get("options")
        if not isinstance(options, list) or not options:
            return None

        selected_value = self._match_choice_value(message_text=message_text, options=options)
        if selected_value is None:
            return None

        base_message = session_context.get("last_effective_message_text") or session_context.get("last_message_text")
        if not isinstance(base_message, str) or not base_message.strip():
            return None

        return FollowUpRewrite(
            kind="ambiguity_choice",
            message_text=f"{base_message}\n{selected_value}".strip(),
        )

    def _match_choice_value(self, *, message_text: str, options: list[dict[str, Any]]) -> str | None:
        normalized = message_text.strip()
        collapsed = self._collapse_text(normalized)

        number_match = CHOICE_NUMBER_PATTERN.fullmatch(normalized)
        if number_match:
            index = int(number_match.group("value")) - 1
            if 0 <= index < len(options):
                return self._option_value(options[index])

        letter_match = CHOICE_LETTER_PATTERN.fullmatch(normalized)
        if letter_match:
            index = ord(letter_match.group("value").lower()) - ord("a")
            if 0 <= index < len(options):
                return self._option_value(options[index])

        for option in options:
            label = str(option.get("label") or "").strip()
            value = self._option_value(option)
            if normalized == label or normalized == value:
                return value

        for option in options:
            label = str(option.get("label") or "").strip()
            value = self._option_value(option)
            label_collapsed = self._collapse_text(label)
            value_collapsed = self._collapse_text(value)
            if not label_collapsed and not value_collapsed:
                continue
            if collapsed and (
                collapsed in label_collapsed
                or label_collapsed in collapsed
                or collapsed in value_collapsed
                or value_collapsed in collapsed
            ):
                return value
        return None

    def _rewrite_missing_input(
        self,
        *,
        message_text: str,
        prompt: dict[str, Any],
    ) -> FollowUpRewrite | None:
        fields = prompt.get("fields")
        if not isinstance(fields, list) or not fields:
            return None

        normalized = message_text.strip()
        if len(fields) == 1:
            field = fields[0]
            key = str(field.get("key") or "").strip()
            if not key:
                return None
            value = self._extract_field_value(
                message_text=normalized,
                key=key,
                label=str(field.get("label") or ""),
            )
            return FollowUpRewrite(kind="missing_input_fill", message_text=f"{key}={value}")

        parts = [part.strip() for part in normalized.split(",")]
        if len(parts) != len(fields) or any(not part for part in parts):
            return None

        assignments = []
        for field, value in zip(fields, parts):
            key = str(field.get("key") or "").strip()
            if not key:
                return None
            extracted_value = self._extract_field_value(
                message_text=value,
                key=key,
                label=str(field.get("label") or ""),
            )
            assignments.append(f"{key}={extracted_value}")
        return FollowUpRewrite(kind="missing_input_fill", message_text=" ".join(assignments))

    @staticmethod
    def _option_value(option: dict[str, Any]) -> str:
        return str(option.get("value") or option.get("label") or "").strip()

    @staticmethod
    def _collapse_text(value: str) -> str:
        return "".join(value.lower().split())

    @staticmethod
    def _extract_field_value(*, message_text: str, key: str, label: str) -> str:
        value = message_text.strip().strip("\"'")
        if not value:
            return ""

        candidates = [token for token in (label, key) if isinstance(token, str) and token.strip()]
        for token in candidates:
            token_pattern = re.escape(token.strip())
            prefix_pattern = re.compile(
                rf"^\s*(?:{token_pattern})\s*(?:은|는|이|가)?\s*(?::|=)?\s*",
                re.IGNORECASE,
            )
            value = prefix_pattern.sub("", value, count=1).strip()

        value = TRAILING_POLITE_SUFFIX_PATTERN.sub("", value).strip()
        value = value.strip("\"'")
        return value or message_text.strip()
