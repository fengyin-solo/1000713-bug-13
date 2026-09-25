"""病害登记业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "disease"
REQUIRED_FIELDS = ["病害编号", "所在设施", "病害类型"]
CONTENT_FIELDS = ["所在设施", "病害类型", "病害位置", "严重等级", "发现日期", "登记人员"]
STATUS_ORDER = ["待定级", "已定级", "处置中", "已闭环", "已挂起"]
ACTION_RULES = {"确认定级": "已定级", "提交闭环": "已闭环", "挂起病害": "已挂起"}
NEGATIVE_ACTIONS = []


def _text(value: Any) -> str:
    return str(value or "").strip()


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
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        existing = self._find_same_disease(rows, values)
        if existing is not None:
            # 同一份病害重复提交：用最新内容覆盖原记录，不再新增，
            # 列表、详情与按设施统计看到的才是同一条数据。
            existing.update({field: values.get(field) for field in REQUIRED_FIELDS})
            return existing, []
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    @staticmethod
    def _find_same_disease(rows: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any] | None:
        """按病害去重：编号相同算同一份；编号不同但内容一模一样也视为重复提交。"""
        number = _text(values.get("病害编号"))
        if number:
            for row in rows:
                if _text(row.get("病害编号")) == number:
                    return row
        for row in rows:
            if all(_text(row.get(field)) == _text(values.get(field)) for field in CONTENT_FIELDS):
                return row
        return None

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
        return entry, f"病害记录已{action}"
