from __future__ import annotations

from ..ledger.constants import CANONICAL_STEP_ORDER


FIELD_ORDER = [
    "기준 GT",
    "비-GT 방향성 문서",
    "주 진행 skill",
    "모델/effort 라우팅",
    "수행한 task",
    "변경한 파일",
    "실행한 검증",
    "validation verdict",
    "progress verdict",
    "progress axes",
    "남은 blocker",
    "다음 task/방향성",
    "완료 여부",
]

STAGE_ORDER = list(CANONICAL_STEP_ORDER)
