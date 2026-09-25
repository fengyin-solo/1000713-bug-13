"""病害登记业务规则：状态流转、字段校验、按病害去重与筛选口径都收在这里。"""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.store import store

MODULE = "disease"
# 可随登记表单维护的业务字段；病害编号以外都允许在编辑时更新。
FIELDS = ["病害编号", "所在设施", "病害类型", "病害位置", "严重等级", "发现日期", "登记人员"]
REQUIRED_FIELDS = ["病害编号", "所在设施", "病害类型"]
# 同一处病害的判定口径：同设施、同类型、同位置即视为同一份病害记录。
IDENTITY_FIELDS = ["所在设施", "病害类型", "病害位置"]
STATUS_ORDER = ["待定级", "已定级", "处置中", "已闭环", "已挂起"]
ACTION_RULES = {"确认定级": "已定级", "提交闭环": "已闭环", "挂起病害": "已挂起"}
NEGATIVE_ACTIONS = []


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _identity(values: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(_clean(values.get(field)) for field in IDENTITY_FIELDS)


class DiseaseService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("病害编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._with_display_status(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._with_display_status(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记病害记录。

        同一设施、同一类型、同一位置的病害视为同一份记录：重复登记不再新建，
        而是把最新一次提交的内容合并到原记录上，编号与状态保持不变，
        返回值第三位 merged 标明本次是否命中了去重。
        """
        cleaned = {field: _clean(values.get(field)) for field in FIELDS if _clean(values.get(field))}
        if not cleaned.get("病害编号"):
            cleaned["病害编号"] = self._next_code()
        missing = [field for field in REQUIRED_FIELDS if not cleaned.get(field)]
        if missing:
            return None, missing, False

        rows = store.rows(MODULE)
        target_identity = _identity(cleaned)
        existing = next(
            (row for row in rows if _identity(row) == target_identity),
            None,
        )
        if existing is not None:
            # 重复登记只保留最新内容；病害编号沿用首登编号，避免统计口径漂移。
            for field in FIELDS[1:]:
                existing[field] = cleaned.get(field, existing.get(field, ""))
            return self._with_display_status(existing), [], True

        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in FIELDS:
            entry[field] = cleaned.get(field, "")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._with_display_status(entry), [], False

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None, list[str]]:
        """按记录编号修改业务字段；修改直接落到存储层，刷新后仍取到新值。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"病害记录 {entry_id} 不存在或已归档", []

        merged = dict(entry)
        for field in FIELDS[1:]:
            if field in values:
                merged[field] = _clean(values.get(field))
        missing = [field for field in REQUIRED_FIELDS if not _clean(merged.get(field))]
        if missing:
            return None, None, missing

        for field in FIELDS[1:]:
            if field in values:
                entry[field] = merged[field]
        return self._with_display_status(entry), None, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"病害记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于病害登记可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._with_display_status(entry), f"病害记录已{action}"

    def get_stats(self) -> dict[str, Any]:
        """统计口径与列表完全一致，都基于去重后的同一份存储数据。"""
        rows = store.rows(MODULE)
        status_counter = Counter(str(row.get("status") or "") for row in rows)
        facility_counter = Counter(_clean(row.get("所在设施")) for row in rows)
        return {
            "total": len(rows),
            "by_status": {status: status_counter.get(status, 0) for status in STATUS_ORDER},
            "by_facility": [
                {"facility": facility, "count": count}
                for facility, count in sorted(facility_counter.items(), key=lambda item: (-item[1], item[0]))
                if facility
            ],
        }

    def _next_code(self) -> str:
        rows = store.rows(MODULE)
        max_seq = 0
        for row in rows:
            code = _clean(row.get("病害编号"))
            if code.startswith("DISE-") and code.removeprefix("DISE-").isdigit():
                max_seq = max(max_seq, int(code.removeprefix("DISE-")))
        return f"DISE-{max_seq + 1:04d}"

    def _with_display_status(self, entry: dict[str, Any]) -> dict[str, Any]:
        # 列表「病害状态」列与内部状态始终取同一个值，避免展示旧状态。
        entry["病害状态"] = entry.get("status")
        return entry
