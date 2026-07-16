"""Static external-advice registry contracts."""

import re

ADVICE_DIR = ".agent_advice"
SENSITIVE_PATTERNS = re.compile(
    r"(api[_-]?key|secret|token|password|credential|private[_-]?key)",
    re.IGNORECASE,
)
FINGERPRINT_CLAIM_RE = re.compile(
    r"(?:output[_ -]?fingerprints?|current[_ -]?output[_ -]?fingerprints?|artifact[_ -]?fingerprints?|fingerprints?)\s*[:=]\s*([A-Za-z0-9_.:/-]{8,128})",
    re.IGNORECASE,
)
ROOT_CAUSE_CLAIM_RE = re.compile(
    r"(?:hypothesized[_ -]?root[_ -]?cause|root[_ -]?cause|root cause|가설|원인)\s*[:=：]\s*`?([A-Za-z0-9가-힣_.:/-]{3,128})`?",
    re.IGNORECASE,
)
ROOT_CAUSE_LEDGER_REL_PATH = ".task/anti_loop/root_cause_ledger.jsonl"
METADATA_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:문서\s*종류|작성일|작성\s*근거|성격|동반\s*문서|advice_id|status|"
    r"not_goal_truth|raw_source_path|received_at|normalized_at|scope|priority|source_label)\s*[:：]",
    re.IGNORECASE,
)
DIRECTIVE_LINE_RE = re.compile(
    r"(?:\bmust\b|\bshould\b|\brequire[sd]?\b|\bdo not\b|\bnever\b|"
    r"규칙|소유|변경|추가|강제|허용|금지|보존|기록|구현|분류|표기|참조|적용|선택|"
    r"게이트|gate|validator|oracle|derive|intake|emit|cap|차단|허용)",
    re.IGNORECASE,
)
CLAIM_LINE_RE = re.compile(
    r"(?:현재|현\s|관측|결함|문제|근거|결과|효과|패턴|기대|원칙|일반\s*근거|"
    r"as-is|to-be|workflow|loop|progress|evidence)",
    re.IGNORECASE,
)
