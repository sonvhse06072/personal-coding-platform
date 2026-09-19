from __future__ import annotations

import re
from typing import Any

from .control_actions import (
    ControlActionService as BaseControlActionService,
    _ADAPTIVE_WORK_SHAPE_DIMENSIONS,
    _BUDGET_EXTENSION_SPECS,
    _BUDGET_FAILURE_MAP,
)


_BUDGET_BLOCK_REASONS = {
    "planner_budget_exhausted",
    "preflight_budget_exhausted",
    "execution_budget_exhausted",
}
_WALL_TIME_RECOVERY_THRESHOLD_MINUTES = 1.0
_LEGACY_COMMAND_TIMEOUT_RE = re.compile(
    r"^(?:RuntimeError|CommandTimeoutError): Command timed out after "
    r"(?P<seconds>\d+(?:\.\d+)?)s(?:\b|:)"
)

_VI_METRIC_LABELS = {
    "Model calls": "Lượt gọi model",
    "Tool calls": "Lượt gọi công cụ",
    "Test runs": "Lượt chạy test",
    "Wall time (min)": "Thời gian (phút)",
    "Repair iterations": "Lượt sửa",
    "Iterations": "Vòng lặp",
    "Model": "Model",
    "Provider": "Provider",
    "Failure kind": "Loại lỗi",
}


class ControlActionService(BaseControlActionService):
    """Owner controls with live budget validation and Vietnamese advisories."""

    @staticmethod
    def _numeric(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _legacy_failed_wall_timeout(cls, job: dict[str, Any]) -> bool:
        """Recognize the pre-1.0.31 wall-bounded timeout shape fail-closed.

        Older Runtime versions persisted command timeouts as generic terminal
        RuntimeError rows before updating elapsed wall time. We accept that legacy
        shape only when the recorded timeout closely matches the wall time that
        remained at the last durable progress checkpoint. This compatibility path
        exists so an already-failed orchestrated job can receive the same bounded
        +20-minute owner action without direct DB mutation or replacement jobs.
        """
        if cls._adaptive_work_shape_nonblocking(job):
            return False
        if str(job.get("status") or "") != "failed":
            return False
        match = _LEGACY_COMMAND_TIMEOUT_RE.match(str(job.get("error") or ""))
        if not match:
            return False
        try:
            timeout_seconds = float(match.group("seconds"))
        except (TypeError, ValueError):
            return False

        route = dict(job.get("route") or {})
        budget = dict((route.get("strategy") or {}).get("budget") or {})
        progress = dict(job.get("progress") or {})
        wall_limit = cls._numeric(budget.get("max_wall_time_minutes"))
        wall_used = cls._numeric(progress.get("elapsed_minutes", 0))
        if wall_limit is None or wall_used is None or timeout_seconds <= 0:
            return False

        remaining_seconds = max(0.0, (wall_limit - wall_used) * 60.0)
        if remaining_seconds <= 10.0 and timeout_seconds <= 10.0:
            return True
        return abs(remaining_seconds - timeout_seconds) <= 30.0

    @classmethod
    def _reassessment_budget_hint(cls, job: dict[str, Any]) -> str | None:
        result = dict(job.get("result") or {})
        if str(result.get("reason") or "") != "reassessment_stopped":
            return None
        reassess = dict(result.get("reassess") or {})
        signals = {str(item) for item in reassess.get("signals") or []}
        if str(reassess.get("action") or "") != "stop" or "hard_budget_guard" not in signals:
            return None
        reason = str(reassess.get("reason") or "")
        if reason not in _BUDGET_FAILURE_MAP:
            return None
        dimension = _BUDGET_FAILURE_MAP[reason]
        if (
            cls._adaptive_work_shape_nonblocking(job)
            and dimension in _ADAPTIVE_WORK_SHAPE_DIMENSIONS
        ):
            return None
        return reason

    @classmethod
    def _budget_hint(cls, job: dict[str, Any]) -> str | None:
        if cls._legacy_failed_wall_timeout(job):
            return "wall-time budget exhausted"
        result = dict(job.get("result") or {})
        reason = str(result.get("reason") or "")
        if reason in _BUDGET_BLOCK_REASONS:
            last_failure = str(result.get("last_failure") or "")
            if last_failure not in _BUDGET_FAILURE_MAP:
                return None
            dimension = _BUDGET_FAILURE_MAP[last_failure]
            if (
                cls._adaptive_work_shape_nonblocking(job)
                and dimension in _ADAPTIVE_WORK_SHAPE_DIMENSIONS
            ):
                return None
            return last_failure
        return cls._reassessment_budget_hint(job)

    @classmethod
    def _is_budget_recovery_state(cls, job: dict[str, Any]) -> bool:
        result = dict(job.get("result") or {})
        reason = str(result.get("reason") or "")
        if cls._adaptive_work_shape_nonblocking(job):
            return cls._legacy_failed_wall_timeout(job) or cls._budget_hint(job) is not None
        return (
            cls._legacy_failed_wall_timeout(job)
            or reason in _BUDGET_BLOCK_REASONS
            or cls._reassessment_budget_hint(job) is not None
        )

    @classmethod
    def _live_budget_dimension(cls, job: dict[str, Any], failure_hint: str) -> str | None:
        if cls._legacy_failed_wall_timeout(job):
            return "max_wall_time_minutes"

        route = dict(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        budget = dict(strategy.get("budget") or {})
        progress = dict(job.get("progress") or {})
        hint = _BUDGET_FAILURE_MAP.get(str(failure_hint or ""))
        adaptive_work_shape = cls._adaptive_work_shape_nonblocking(job)
        if adaptive_work_shape and hint in _ADAPTIVE_WORK_SHAPE_DIMENSIONS:
            hint = None

        exhausted: list[str] = []
        for dimension, spec in _BUDGET_EXTENSION_SPECS.items():
            if adaptive_work_shape and dimension in _ADAPTIVE_WORK_SHAPE_DIMENSIONS:
                continue
            if dimension not in budget:
                continue
            used = cls._numeric(progress.get(spec["counter"], 0))
            limit = cls._numeric(budget.get(dimension))
            if used is None or limit is None:
                continue
            if used >= limit:
                exhausted.append(dimension)

        if len(exhausted) == 1:
            return exhausted[0]
        if len(exhausted) > 1:
            # A structured current failure may disambiguate only when that same
            # dimension is also confirmed exhausted by the live durable counters.
            return hint if hint in exhausted else None

        if adaptive_work_shape:
            return None

        wall_spec = _BUDGET_EXTENSION_SPECS["max_wall_time_minutes"]
        wall_used = cls._numeric(progress.get(wall_spec["counter"], 0))
        wall_limit = cls._numeric(budget.get("max_wall_time_minutes"))
        if wall_used is not None and wall_limit is not None:
            remaining = wall_limit - wall_used
            if 0 <= remaining <= _WALL_TIME_RECOVERY_THRESHOLD_MINUTES:
                return "max_wall_time_minutes"

        return None

    @staticmethod
    def _vi_budget_label(dimension: str, increment: int) -> str:
        labels = {
            "max_model_calls": "lượt gọi model",
            "max_tool_calls": "lượt gọi công cụ",
            "max_test_runs": "lượt chạy test",
            "max_wall_time_minutes": "phút",
            "max_repair_iterations": "lượt sửa",
            "max_iterations": "vòng lặp",
        }
        return f"➕ +{increment} {labels.get(dimension, 'ngân sách')}"

    @staticmethod
    def _localize_metric_labels(advisory: dict[str, Any]) -> None:
        for metric in advisory.get("metrics") or []:
            if not isinstance(metric, dict):
                continue
            label = str(metric.get("label") or "")
            if label in _VI_METRIC_LABELS:
                metric["label"] = _VI_METRIC_LABELS[label]

    @classmethod
    def _localize_action_labels(cls, advisory: dict[str, Any]) -> None:
        fixed = {
            "details": "📋 Chi tiết",
            "keep_blocked": "⛔ Giữ trạng thái chặn",
            "provider_quota_reset": "✅ Quota đã reset — tiếp tục",
            "reroute_provider": "🔀 Chuyển provider",
            "retry_provider": "🔁 Thử lại provider",
            "provider_credentials_fixed": "✅ Đã sửa credentials — thử lại",
            "reroute_retry": "🔀 Định tuyến lại + thử lại",
            "retry_delivery": "🔁 Thử lại delivery",
            "recheck_ci": "🔄 Kiểm tra lại CI",
            "resume_same": "▶️ Tiếp tục cùng job",
            "resume_reroute": "🔀 Tiếp tục + định tuyến lại",
            "human_decision_approve": "✅ Phê duyệt",
            "human_decision_reject": "❌ Từ chối",
            "operator_complete": "✅ Đánh dấu hoàn tất",
            "operator_block": "⛔ Đánh dấu bị chặn",
            "recheck_orchestration": "🔄 Tôi đã merge — kiểm tra lại",
            "url": "🔗 Mở PR",
        }
        for action in advisory.get("action_specs") or []:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("action_type") or "")
            if action_type == "budget_extend":
                payload = dict(action.get("payload") or {})
                dimension = str(payload.get("dimension") or "")
                increment = int(payload.get("increment") or 0)
                action["label"] = cls._vi_budget_label(dimension, increment)
            elif action_type in fixed:
                action["label"] = fixed[action_type]

    @classmethod
    def _localize_blocked_advisory(cls, advisory: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        reason = str(advisory.get("reason") or "")
        action_types = {
            str(item.get("action_type") or "")
            for item in advisory.get("action_specs") or []
            if isinstance(item, dict)
        }
        advisory["title"] = "WORKORDER BỊ CHẶN"
        advisory["preserved"] = [
            "Giữ nguyên cùng job và workspace khi có.",
            "Giữ nguyên diff, tiến độ và các bộ đếm sử dụng bền vững.",
            "Các WorkOrder phía sau tiếp tục chờ cho đến khi các gate hiện tại được thỏa mãn.",
        ]
        advisory["impact"] = "Không có tác vụ tự động nào chạy tiếp cho WorkOrder này cho đến khi một action khôi phục hợp lệ thành công."

        if self_legacy := cls._legacy_failed_wall_timeout(job):
            advisory["summary"] = "Runtime cũ đã ghi terminal failure khi coding-agent timeout đúng tại wall-time deadline."
            advisory["cause"] = "Timeout này khớp với phần wall-time còn lại của job; same-job recovery cần mở rộng wall-time có giới hạn."
            advisory["recommended"] = "Chỉ phê duyệt +20 phút để tiếp tục đúng job/workspace hiện tại sau khi Runtime fix đã được rollout."
        elif reason in _BUDGET_BLOCK_REASONS:
            advisory["summary"] = "Runtime đã dùng hết một giới hạn ngân sách thực thi."
            advisory["cause"] = "Một giới hạn an toàn của Runtime đã chạm ngưỡng hiện tại; đây không phải quota rolling của provider."
        elif reason == "reassessment_stopped" and cls._reassessment_budget_hint(job):
            advisory["summary"] = "Reassessment dừng vì Definition of Done chưa đạt và ngân sách hiện tại không cho phép chạy thêm."
            advisory["cause"] = "Reassessment báo hard_budget_guard; Runtime chỉ cho phép mở rộng đúng dimension đang bị chặn theo live counters."
        elif reason in {"reassessment_stopped", "unsafe_bare_completion"}:
            advisory["summary"] = "Runtime không cho phép tiếp tục hoặc tự động hoàn tất sau reassessment."
            advisory["cause"] = "Trạng thái Definition of Done/reassessment hiện tại không cho phép tự động hoàn tất."
            advisory["recommended"] = "Kiểm tra WorkOrder và decision boundary hiện tại. Cố ý không có action force-complete."
        elif reason in {"planner_provider_failure_without_fallback", "provider_failure_without_fallback", "evaluator_provider_failure_without_fallback"}:
            advisory["summary"] = "Provider/model thất bại và không có fallback hợp lệ hoàn tất phase."
            if "provider_quota_reset" in action_types:
                advisory["cause"] = "Provider báo đã hết quota; trạng thái job vẫn được giữ nguyên."
                advisory["recommended"] = "Chờ quota provider reset rồi xác nhận để tiếp tục, hoặc chuyển provider nếu policy cho phép."
            elif "retry_provider" in action_types:
                advisory["cause"] = "Provider đang tạm thời unavailable, timeout hoặc rate limit."
                advisory["recommended"] = "Thử lại provider hoặc yêu cầu định tuyến sang provider hợp lệ khác."
            elif "provider_credentials_fixed" in action_types:
                advisory["cause"] = "Authentication hoặc cấu hình provider cần được operator sửa bên ngoài Telegram."
                advisory["recommended"] = "Sửa credentials/cấu hình provider, sau đó xác nhận để thử lại."
            else:
                advisory["cause"] = "Provider/model thất bại với loại lỗi chưa có recovery tự động an toàn."
                advisory["recommended"] = "Chỉ định tuyến lại khi policy tìm được provider hợp lệ; nếu không hãy giữ trạng thái chặn."
        elif reason == "material_change_missing_without_model_fallback":
            advisory["summary"] = "Coding agent hoàn tất nhưng chưa tạo material repository change bắt buộc."
            advisory["cause"] = "Runtime không tìm được model fallback hợp lệ sau một lần chạy không tạo thay đổi cần thiết."
            advisory["recommended"] = "Định tuyến lại và thử lại trong đúng phạm vi WorkOrder hiện tại."
        elif reason == "preflight_failed":
            advisory["summary"] = "Deterministic preflight verification thất bại."
            advisory["cause"] = "Một preflight check đã thất bại; raw command output cố ý không được gửi qua Telegram."
            advisory["recommended"] = "Kiểm tra lỗi verification bên ngoài Telegram trước khi thử lại."
        elif reason in {"github_delivery_failed", "github_ci_timeout"}:
            advisory["summary"] = "Kết quả đã verify local đang bị chặn ở bước GitHub delivery/CI."
            advisory["cause"] = "Kết quả local đã được giữ nguyên; Runtime không cần code lại trước khi retry delivery."
            advisory["recommended"] = "Thử lại delivery hoặc kiểm tra lại CI mà không thay đổi kết quả đã được chấp nhận."
        elif reason == "github_delivery_budget_exhausted":
            advisory["summary"] = "GitHub delivery đã hết ngân sách wall-time của Runtime."
            advisory["cause"] = "Kết quả local đã verify vẫn được giữ nguyên nhưng không còn thời gian delivery."
            advisory["recommended"] = "Phê duyệt mở rộng wall-time có giới hạn rồi thử lại cùng trạng thái delivery."
        elif reason == "delivery_missing_verified_commit":
            advisory["summary"] = "Delivery không thể tiếp tục vì kết quả được chấp nhận chưa có verified commit."
            advisory["cause"] = "Runtime không tự tạo commit giả hoặc ép GitHub delivery."
            advisory["recommended"] = "Kiểm tra kết quả local đã giữ nguyên và sửa delivery invariant bên ngoài Telegram."
        elif str(job.get("status") or "") == "interrupted":
            advisory["summary"] = "Runtime bị gián đoạn và cần recovery rõ ràng trên cùng job."
            advisory["cause"] = "Process trước đã dừng; job/workspace bền vững vẫn được giữ nguyên."
            advisory["recommended"] = "Tiếp tục cùng job; chỉ yêu cầu định tuyến lại nếu cần."
        else:
            advisory["summary"] = "WorkOrder đang bị chặn và cần owner xử lý."
            advisory["cause"] = "Runtime đã dừng an toàn tại một control gate bền vững."
            advisory["recommended"] = "Kiểm tra chi tiết an toàn và chỉ chọn action có giới hạn đang được cung cấp."

        cls._localize_metric_labels(advisory)
        cls._localize_action_labels(advisory)
        return advisory

    def blocked_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        advisory = super().blocked_advisory(work_order, job)
        current_job = dict(job or {})

        if self._is_budget_recovery_state(current_job):
            failure_hint = self._budget_hint(current_job) or ""
            dimension = self._live_budget_dimension(current_job, failure_hint)

            advisory["action_specs"] = [
                item
                for item in advisory.get("action_specs") or []
                if str(item.get("action_type") or "") != "budget_extend"
            ]

            if dimension is None:
                advisory["cause"] = (
                    "Runtime báo hết ngân sách nhưng live counters hiện tại không xác định được một dimension duy nhất có thể mở rộng an toàn."
                )
                advisory["recommended"] = "Giữ WorkOrder ở trạng thái chặn và kiểm tra budget hiện tại trước khi mở rộng bất kỳ giới hạn nào."
            else:
                spec = _BUDGET_EXTENSION_SPECS[dimension]
                metric = self._budget_metric(current_job, dimension)
                if metric and not any(
                    isinstance(item, dict) and item.get("key") == dimension
                    for item in advisory.get("metrics") or []
                ):
                    advisory.setdefault("metrics", []).insert(0, metric)
                advisory["recommended"] = (
                    f"Chỉ phê duyệt mở rộng +{spec['increment']} nếu WorkOrder hiện tại vẫn cần thêm một lượt thực thi/verification."
                )
                advisory.setdefault("action_specs", []).insert(
                    0,
                    {
                        "action_type": "budget_extend",
                        "label": self._vi_budget_label(dimension, int(spec["increment"])),
                        "payload": {"dimension": dimension, "increment": spec["increment"]},
                    },
                )

        return self._localize_blocked_advisory(advisory, current_job)

    def waiting_human_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        advisory = super().waiting_human_advisory(work_order, job)
        if str(work_order.get("execution_mode") or "") == "operator":
            advisory.update({
                "title": "CẦN OPERATOR THỰC HIỆN",
                "summary": "Một operator WorkOrder đang chờ owner xác nhận.",
                "cause": "Plan yêu cầu rõ ràng một bước human/operator trước khi dependency phía sau được tiếp tục.",
                "preserved": ["Các WorkOrder phía sau tiếp tục chờ."],
                "impact": "Automation không vượt qua operator gate này cho đến khi owner xử lý.",
                "recommended": "Thực hiện đúng procedure đã được tài liệu hóa, sau đó đánh dấu hoàn tất hoặc bị chặn.",
            })
        else:
            advisory.update({
                "title": "CẦN QUYẾT ĐỊNH CỦA OWNER",
                "summary": "Runtime đang chờ một quyết định rõ ràng từ owner.",
                "cause": "Một governance decision boundary đã cấu hình yêu cầu owner phê duyệt trước khi tiếp tục.",
                "preserved": ["Giữ nguyên cùng job/workspace và tiến độ bền vững."],
                "impact": "Job không tiếp tục cho đến khi exact durable decision này được xử lý.",
                "recommended": "Chỉ phê duyệt nếu decision boundary của WorkOrder là chấp nhận được; nếu không hãy từ chối.",
            })
        self._localize_action_labels(advisory)
        return advisory

    @classmethod
    def manual_merge_advisory(cls, pr_url: str | None) -> dict[str, Any]:
        advisory = super().manual_merge_advisory(pr_url)
        advisory.update({
            "title": "CẦN MERGE THỦ CÔNG",
            "summary": "PR đã qua các gate tự động và đang chờ owner merge thủ công.",
            "cause": "Platform cố ý không bao giờ auto-merge công việc cần owner review.",
            "preserved": ["Các WorkOrder phía sau tiếp tục chờ cho đến khi Runtime quan sát thấy PR đã merge."],
            "impact": "Plan chưa thể chuyển qua WorkOrder này.",
            "recommended": "Mở PR, review và merge thủ công, sau đó yêu cầu Runtime kiểm tra lại orchestration.",
        })
        cls._localize_action_labels(advisory)
        return advisory

    def _apply_budget_extension(self, action: dict[str, Any]) -> dict[str, Any]:
        job_id = str(action.get("job_id") or "")
        if not job_id:
            raise RuntimeError("Budget extension requires a Runtime job")
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        if not self._is_budget_recovery_state(job):
            raise RuntimeError("Budget extension no longer matches a budget-exhausted Runtime state")

        payload = dict(action.get("payload") or {})
        requested = str(payload.get("dimension") or "")
        current = self._live_budget_dimension(job, self._budget_hint(job) or "")
        if not current or current != requested:
            raise RuntimeError("Budget extension is stale or does not match the current live exhausted dimension")

        return super()._apply_budget_extension(action)


__all__ = ["ControlActionService"]
