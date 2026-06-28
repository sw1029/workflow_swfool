#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


PACK_STATUSES = {"active", "completed", "blocked", "terminal_blocked", "superseded"}
ITEM_STATUSES = {
    "planned",
    "promoted",
    "in_progress",
    "consumed",
    "inserted",
    "reordered",
    "skipped",
    "blocked",
    "terminal_blocked",
    "superseded",
}
VALIDATION_PROFILES = {"current_only", "affected_chain", "full_chain"}
PROGRESS_TARGETS = {"advanced", "safety_only", "no_progress", "regressed"}
PROGRESS_KINDS = {"goal_productive", "governance_only"}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def pack_dir(root: Path) -> Path:
    return root / ".task" / "task_pack"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load task pack {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Task pack must be a JSON object: {path}")
    return value


def load_plan(value: str | None) -> dict[str, Any]:
    if not value or value == "-":
        raw = sys.stdin.read()
        plan = json.loads(raw) if raw.strip() else {}
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            plan = json.loads(stripped)
        else:
            path = Path(stripped)
            plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise SystemExit("Mutation plan must be a JSON object.")
    return plan


def write_json(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pack_paths(root: Path) -> list[Path]:
    directory = pack_dir(root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def validate_pack(data: dict[str, Any], path: Path | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(severity: str, code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        findings.append(item)

    for field in ("schema_version", "pack_id", "status", "goal", "items", "mutation_log"):
        if field not in data:
            add("block", "missing_required_field", f"Task pack is missing `{field}`.", {"path": str(path) if path else None})
    if data.get("schema_version") != 1:
        add("block", "unsupported_schema_version", "`schema_version` must be 1.", {"value": data.get("schema_version")})
    status = data.get("status")
    if status not in PACK_STATUSES:
        add("block", "invalid_pack_status", "Invalid task pack status.", {"status": status})

    items = data.get("items")
    if not isinstance(items, list) or not items:
        add("block", "items_missing", "`items` must be a non-empty list.")
        return findings

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            add("block", "invalid_item", "Task pack item must be an object.", {"index": index})
            continue
        for field in ("item_id", "order", "status", "title", "objective", "validation_profile", "progress_target"):
            if field not in item:
                add("block", "missing_item_field", f"Task pack item is missing `{field}`.", {"index": index})
        item_id = str(item.get("item_id") or "")
        if not item_id:
            add("block", "empty_item_id", "Task pack item has empty item_id.", {"index": index})
        elif item_id in seen_ids:
            add("block", "duplicate_item_id", "Task pack item_id is duplicated.", {"item_id": item_id})
        seen_ids.add(item_id)
        order = item.get("order")
        if not isinstance(order, int) or order <= 0:
            add("block", "invalid_item_order", "Task pack item order must be a positive integer.", {"item_id": item_id, "order": order})
        elif order in seen_orders:
            add("block", "duplicate_item_order", "Task pack item order is duplicated.", {"order": order})
        seen_orders.add(order) if isinstance(order, int) else None
        if item.get("status") not in ITEM_STATUSES:
            add("block", "invalid_item_status", "Invalid task pack item status.", {"item_id": item_id, "status": item.get("status")})
        if item.get("validation_profile") not in VALIDATION_PROFILES:
            add("warn", "invalid_validation_profile", "Unexpected validation profile.", {"item_id": item_id, "validation_profile": item.get("validation_profile")})
        if item.get("progress_target") not in PROGRESS_TARGETS:
            add("warn", "invalid_progress_target", "Unexpected progress target.", {"item_id": item_id, "progress_target": item.get("progress_target")})
        progress_kind_expected = item.get("progress_kind_expected")
        if progress_kind_expected is not None and progress_kind_expected not in PROGRESS_KINDS:
            add(
                "warn",
                "invalid_progress_kind_expected",
                "`progress_kind_expected` should be goal_productive or governance_only.",
                {"item_id": item_id, "progress_kind_expected": progress_kind_expected},
            )
        if progress_kind_expected == "goal_productive" and item.get("progress_target") in {"safety_only", "no_progress"}:
            add(
                "warn",
                "progress_kind_target_mismatch",
                "A goal_productive pack item should not declare a safety_only/no_progress progress target.",
                {"item_id": item_id, "progress_target": item.get("progress_target")},
            )
        if item.get("positive_input_delta_required") is True and not item.get("required_new_input_kinds"):
            add("block", "positive_delta_kinds_missing", "Positive input delta gate requires `required_new_input_kinds`.", {"item_id": item_id})
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if item.get("positive_input_delta_required") is True and item.get("status") in {"consumed", "terminal_blocked"}:
            gate = result.get("positive_input_delta_gate") if isinstance(result.get("positive_input_delta_gate"), dict) else {}
            has_supplied = bool(
                result.get("has_supplied_input_delta")
                or gate.get("has_supplied_input_delta")
                or result.get("produced_domain_delta")
                or gate.get("produced_domain_delta")
                or result.get("supplied_input_artifact_paths")
                or gate.get("supplied_input_artifact_paths")
            )
            if not has_supplied:
                add(
                    "warn",
                    "consumed_item_missing_supplied_input_delta",
                    "Consumed evidence-family pack items should record a supplied input artifact or produced_domain_delta=true; derive/result-contract gates enforce this for new progress claims.",
                    {"item_id": item_id},
                )

    current = data.get("current_item_id")
    if current and current not in seen_ids:
        add("block", "current_item_missing", "`current_item_id` does not match any item.", {"current_item_id": current})
    if data.get("status") == "terminal_blocked" and not data.get("terminal_blocker"):
        add("block", "terminal_blocker_missing", "`terminal_blocked` pack requires `terminal_blocker`.")
    terminal = data.get("terminal_blocker")
    if isinstance(terminal, dict):
        for field in ("semantic_signature", "blocker_signature", "required_handoff", "evidence_paths"):
            if not terminal.get(field):
                add("block", "terminal_blocker_field_missing", f"`terminal_blocker` requires `{field}`.", {"field": field})
        if terminal.get("provider_reattempt_required") is True:
            add(
                "block",
                "provider_terminal_seal_before_bounded_retry",
                "Task pack cannot terminal-block a provider family while bounded provider retry is still required.",
            )
        if terminal.get("authorized_alternative_path_exists") is True and not terminal.get("authorized_alternative_path_attempted"):
            add(
                "block",
                "seal_denied_authorized_alternative_unattempted",
                "Task pack cannot seal a family while an authority-permitted productive alternative remains unattempted.",
            )
        if terminal.get("untried_actionable_root_cause_exists") is True:
            add(
                "block",
                "seal_denied_untried_actionable_root_cause",
                "Task pack cannot terminal-block while a local, bounded, provider-free, in-scope, authority-allowed root-cause hypothesis remains untried.",
            )
        if terminal.get("terminal_quiescence") is True and terminal.get("commit_skipped_reason") != "terminal_quiescence":
            add(
                "warn",
                "terminal_quiescence_missing_commit_skip_reason",
                "Terminal quiescence should record `commit_skipped_reason: terminal_quiescence` to prevent closeout/report/recheck reproduction.",
            )
    if not isinstance(data.get("mutation_log", []), list):
        add("block", "mutation_log_invalid", "`mutation_log` must be a list.")
    return findings


def status_from_findings(findings: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "block" for item in findings):
        return "block"
    if findings:
        return "warn"
    return "ok"


def active_pack(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in pack_paths(root):
        data = load_json(path)
        loaded.append((path, data))
        if data.get("status") == "active":
            return path, data
    return loaded[0] if loaded else (None, None)


def sorted_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((item for item in data.get("items", []) if isinstance(item, dict)), key=lambda item: item.get("order", 0))


def item_order(data: dict[str, Any]) -> list[str]:
    return [str(item.get("item_id")) for item in sorted_items(data) if item.get("item_id")]


def renumber_items(data: dict[str, Any]) -> None:
    for index, item in enumerate(sorted_items(data), start=1):
        item["order"] = index


def planned_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sorted_items(data) if item.get("status") in {"planned", "inserted", "reordered", "blocked"}]


def refresh_current_item(data: dict[str, Any]) -> None:
    remaining = [item for item in planned_items(data) if item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    if not remaining and data.get("status") == "active":
        data["status"] = "completed"


def evidence_paths_from(plan: dict[str, Any]) -> list[str]:
    value = plan.get("evidence_paths") or plan.get("evidence") or []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def mutation_entry(action: str, plan: dict[str, Any], before_order: list[str], after_order: list[str]) -> dict[str, Any]:
    reason = str(plan.get("reason") or plan.get("mutation_reason") or "").strip()
    if not reason:
        raise SystemExit("Mutation plan requires `reason`.")
    return {
        "timestamp": now_iso(),
        "action": action,
        "reason": reason,
        "evidence_paths": evidence_paths_from(plan),
        "before_order": before_order,
        "after_order": after_order,
        "actor": "$derive-improvement-task",
    }


def next_item(data: dict[str, Any]) -> dict[str, Any] | None:
    current = data.get("current_item_id")
    items = sorted_items(data)
    if current:
        for item in items:
            if item.get("item_id") == current and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                return item
    for item in items:
        if item.get("status") in {"planned", "inserted", "reordered"}:
            return item
    return None


def render_markdown(root: Path, path: Path, data: dict[str, Any], language: str) -> str:
    ko = language.lower().startswith("ko")
    title = "Task Pack" if not ko else "Task Pack"
    labels = {
        "status": "Status" if not ko else "상태",
        "goal": "Goal" if not ko else "목표",
        "current": "Current Item" if not ko else "현재 item",
        "terminal": "Terminal Blocker" if not ko else "terminal blocker",
        "items": "Items" if not ko else "Items",
        "mutations": "Mutation Log" if not ko else "Mutation Log",
    }
    lines = [
        f"# {title}: {data.get('pack_id', path.stem)}",
        "",
        f"- {labels['status']}: {data.get('status')}",
        f"- {labels['goal']}: {data.get('goal')}",
        f"- {labels['current']}: {data.get('current_item_id') or 'none'}",
        f"- JSON: `{rel_path(root, path)}`",
        "",
        f"## {labels['items']}",
        "",
    ]
    for item in sorted_items(data):
        lines.extend(
            [
                f"### {item.get('order')}. {item.get('title')}",
                "",
                f"- item_id: `{item.get('item_id')}`",
                f"- status: `{item.get('status')}`",
                f"- progress_target: `{item.get('progress_target')}`",
                f"- progress_kind_expected: `{item.get('progress_kind_expected') or 'none'}`",
                f"- validation_profile: `{item.get('validation_profile')}`",
                f"- semantic_signature_expected: `{item.get('semantic_signature_expected') or 'none'}`",
                f"- positive_input_delta_required: `{item.get('positive_input_delta_required', False)}`",
                f"- required_new_input_kinds: {', '.join(str(value) for value in item.get('required_new_input_kinds', [])) or 'none'}",
                "",
                str(item.get("objective") or "").strip(),
                "",
            ]
        )
    if data.get("terminal_blocker"):
        lines.extend([f"## {labels['terminal']}", "", "```json", json.dumps(data["terminal_blocker"], ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    if data.get("mutation_log"):
        lines.extend([f"## {labels['mutations']}", ""])
        for mutation in data.get("mutation_log", []):
            if isinstance(mutation, dict):
                lines.append(f"- {mutation.get('timestamp')}: {mutation.get('action')} - {mutation.get('reason')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_path(path: Path) -> Path:
    return path.with_suffix(".md")


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path, data = active_pack(root)
    if not path or not data:
        output = {"status": "not_applicable", "active_pack": None, "pack_count": 0}
    else:
        findings = validate_pack(data, path)
        item = next_item(data)
        output = {
            "status": status_from_findings(findings),
            "active_pack": rel_path(root, path),
            "render_path": rel_path(root, render_path(path)) if render_path(path).exists() else None,
            "pack_id": data.get("pack_id"),
            "pack_status": data.get("status"),
            "goal": data.get("goal"),
            "current_item_id": data.get("current_item_id"),
            "next_item": item,
            "planned_item_count": sum(1 for item_data in data.get("items", []) if isinstance(item_data, dict) and item_data.get("status") in {"planned", "inserted", "reordered"}),
            "terminal_blocker": data.get("terminal_blocker"),
            "findings": findings,
            "pack_count": len(pack_paths(root)),
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] not in {"block"} else 2


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = [root / args.pack] if args.pack else pack_paths(root)
    results = []
    status = "ok"
    for path in paths:
        data = load_json(path)
        findings = validate_pack(data, path)
        result_status = status_from_findings(findings)
        if result_status == "block":
            status = "block"
        elif result_status == "warn" and status == "ok":
            status = "warn"
        results.append({"path": rel_path(root, path), "status": result_status, "findings": findings})
    output = {"status": status, "results": results, "pack_count": len(results)}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if status != "block" else 2


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = [root / args.pack] if args.pack else pack_paths(root)
    rendered = []
    for path in paths:
        data = load_json(path)
        findings = validate_pack(data, path)
        if any(item.get("severity") == "block" for item in findings):
            rendered.append({"path": rel_path(root, path), "status": "block", "findings": findings})
            continue
        output_path = render_path(path)
        output_path.write_text(render_markdown(root, path, data, args.language), encoding="utf-8")
        rendered.append({"path": rel_path(root, path), "status": "rendered", "render_path": rel_path(root, output_path), "findings": findings})
    output = {"status": "block" if any(item["status"] == "block" for item in rendered) else "ok", "rendered": rendered}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


def command_next(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path, data = active_pack(root)
    if not path or not data:
        output = {"status": "not_applicable", "next_item": None}
    else:
        item = next_item(data)
        output = {
            "status": "ok" if item else "terminal_candidate",
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "next_item": item,
            "terminal_blocker": data.get("terminal_blocker"),
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    mapping = {
        "insert_items": "insert",
        "insert_item": "insert",
        "reorder_items": "reorder",
        "skip_items": "skip",
        "exclude_items": "skip",
        "supersede_pack": "supersede",
        "terminal_blocked": "terminal_block",
        "terminal_block": "terminal_block",
        "create_pack": "create",
    }
    return mapping.get(normalized, normalized)


def command_apply_mutation(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    plan = load_plan(args.plan)
    action = normalize_action(args.action or str(plan.get("action") or plan.get("pack_disposition") or ""))
    if action not in {"insert", "reorder", "skip", "supersede", "terminal_block", "create"}:
        raise SystemExit("Mutation action must be insert, reorder, skip, supersede, terminal_block, or create.")

    if action == "create":
        pack_data = plan.get("pack") if isinstance(plan.get("pack"), dict) else plan
        pack_id = str(pack_data.get("pack_id") or "").strip()
        if not pack_id:
            raise SystemExit("Create mutation requires `pack_id`.")
        path = pack_dir(root) / f"{pack_id}.json"
        if path.exists():
            raise SystemExit(f"Task pack already exists: {rel_path(root, path)}")
        pack_data.setdefault("schema_version", 1)
        pack_data.setdefault("status", "active")
        pack_data.setdefault("language", args.language)
        pack_data.setdefault("created_at", now_iso())
        pack_data.setdefault("updated_at", now_iso())
        pack_data.setdefault("mutation_log", [])
        pack_data.setdefault("terminal_blocker", None)
        if not pack_data.get("current_item_id") and isinstance(pack_data.get("items"), list) and pack_data["items"]:
            pack_data["current_item_id"] = sorted(pack_data["items"], key=lambda item: item.get("order", 0))[0].get("item_id")
        pack_data.setdefault("mutation_log", []).append(mutation_entry("create", plan, [], item_order(pack_data)))
        findings = validate_pack(pack_data, path)
        if any(item.get("severity") == "block" for item in findings):
            output = {"status": "block", "pack_path": rel_path(root, path), "findings": findings}
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        write_json(path, pack_data)
        render_output_path = None
        if args.render:
            render_output_path = render_path(path)
            render_output_path.write_text(render_markdown(root, path, pack_data, args.language), encoding="utf-8")
        output = {
            "status": "ok",
            "action": "create",
            "pack_path": rel_path(root, path),
            "render_path": rel_path(root, render_output_path) if render_output_path else None,
            "pack_id": pack_data.get("pack_id"),
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    path = root / str(plan.get("pack_path") or args.pack) if (plan.get("pack_path") or args.pack) else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    before_order = item_order(data)
    items = data.get("items")
    if not isinstance(items, list):
        raise SystemExit("Task pack has invalid `items`.")

    if action == "insert":
        new_items = plan.get("items") or plan.get("insert_items")
        if not isinstance(new_items, list) or not new_items:
            raise SystemExit("Insert mutation requires non-empty `items`.")
        existing_ids = {str(item.get("item_id")) for item in items if isinstance(item, dict)}
        for item in new_items:
            if not isinstance(item, dict):
                raise SystemExit("Inserted items must be JSON objects.")
            item_id = str(item.get("item_id") or "").strip()
            if not item_id or item_id in existing_ids:
                raise SystemExit(f"Inserted item_id is empty or duplicated: {item_id}")
            item.setdefault("status", "inserted")
            item.setdefault("dependencies", [])
            item.setdefault("source_evidence", evidence_paths_from(plan))
            item.setdefault("promotion", {"task_id": None, "task_path": None, "promoted_at": None})
            item.setdefault("result", {"validation_verdict": None, "progress_verdict": None, "progress_kind": None, "semantic_signature": None, "blocker_signature": None})
            existing_ids.add(item_id)
        insert_before = plan.get("insert_before_item_id") or data.get("current_item_id")
        rebuilt: list[dict[str, Any]] = []
        inserted = False
        for item in sorted_items(data):
            if insert_before and item.get("item_id") == insert_before:
                rebuilt.extend(new_items)
                inserted = True
            rebuilt.append(item)
        if not inserted:
            rebuilt.extend(new_items)
        data["items"] = rebuilt
        renumber_items(data)
        data.setdefault("mutation_log", []).append(mutation_entry("insert", plan, before_order, item_order(data)))

    elif action == "reorder":
        requested = plan.get("item_order") or plan.get("order")
        if not isinstance(requested, list) or not requested:
            raise SystemExit("Reorder mutation requires full `item_order` list.")
        requested_ids = [str(item) for item in requested]
        current_ids = item_order(data)
        if set(requested_ids) != set(current_ids) or len(requested_ids) != len(current_ids):
            raise SystemExit("Reorder mutation must name every existing item exactly once.")
        by_id = {str(item.get("item_id")): item for item in items if isinstance(item, dict)}
        data["items"] = [by_id[item_id] for item_id in requested_ids]
        for item in data["items"]:
            if item.get("status") == "planned":
                item["status"] = "reordered"
        renumber_items(data)
        data.setdefault("mutation_log", []).append(mutation_entry("reorder", plan, before_order, item_order(data)))

    elif action == "skip":
        item_ids = plan.get("item_ids") or plan.get("skip_item_ids") or plan.get("exclude_item_ids")
        if not isinstance(item_ids, list) or not item_ids:
            raise SystemExit("Skip mutation requires non-empty `item_ids`.")
        targets = {str(item_id) for item_id in item_ids}
        found: set[str] = set()
        for item in items:
            if isinstance(item, dict) and str(item.get("item_id")) in targets:
                item["status"] = "skipped"
                result = item.setdefault("result", {})
                result["skip_reason"] = plan.get("reason")
                result["evidence_paths"] = evidence_paths_from(plan)
                found.add(str(item.get("item_id")))
        missing = sorted(targets - found)
        if missing:
            raise SystemExit(f"Unknown task pack item(s): {', '.join(missing)}")
        data.setdefault("mutation_log", []).append(mutation_entry("skip", plan, before_order, item_order(data)))

    elif action == "supersede":
        data["status"] = "superseded"
        for item in items:
            if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "superseded"
        data.setdefault("mutation_log", []).append(mutation_entry("supersede", plan, before_order, item_order(data)))

    elif action == "terminal_block":
        terminal = plan.get("terminal_blocker")
        if not isinstance(terminal, dict):
            raise SystemExit("terminal_block mutation requires `terminal_blocker` object.")
        data["status"] = "terminal_blocked"
        data["terminal_blocker"] = terminal
        current = data.get("current_item_id")
        for item in items:
            if isinstance(item, dict) and (not current or item.get("item_id") == current) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "terminal_blocked"
                break
        data.setdefault("mutation_log", []).append(mutation_entry("terminal_block", plan, before_order, item_order(data)))

    refresh_current_item(data)
    findings = validate_pack(data, path)
    if any(item.get("severity") == "block" for item in findings):
        output = {"status": "block", "action": action, "pack_path": rel_path(root, path), "findings": findings}
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    write_json(path, data)
    render_output_path = None
    if args.render:
        render_output_path = render_path(path)
        render_output_path.write_text(render_markdown(root, path, data, args.language), encoding="utf-8")
    output = {
        "status": "ok",
        "action": action,
        "pack_path": rel_path(root, path),
        "render_path": rel_path(root, render_output_path) if render_output_path else None,
        "pack_id": data.get("pack_id"),
        "pack_status": data.get("status"),
        "current_item_id": data.get("current_item_id"),
        "before_order": before_order,
        "after_order": item_order(data),
        "findings": findings,
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_mark_consumed(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = root / args.pack if args.pack else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    found = False
    for item in data.get("items", []):
        if isinstance(item, dict) and item.get("item_id") == args.item_id:
            item["status"] = "consumed"
            promotion = item.setdefault("promotion", {})
            if args.task_id:
                promotion["task_id"] = args.task_id
            if args.task_path:
                promotion["task_path"] = args.task_path
            promotion.setdefault("promoted_at", now_iso())
            result = item.setdefault("result", {})
            for key, value in (
                ("validation_verdict", args.validation_verdict),
                ("progress_verdict", args.progress_verdict),
                ("progress_kind", args.progress_kind),
                ("semantic_signature", args.semantic_signature),
                ("blocker_signature", args.blocker_signature),
            ):
                if value:
                    result[key] = value
            if args.has_supplied_input_delta:
                gate = result.setdefault("positive_input_delta_gate", {})
                gate["has_supplied_input_delta"] = True
            if args.supplied_input_artifact_path:
                gate = result.setdefault("positive_input_delta_gate", {})
                paths = gate.setdefault("supplied_input_artifact_paths", [])
                for supplied_path in args.supplied_input_artifact_path:
                    if supplied_path not in paths:
                        paths.append(supplied_path)
            found = True
            break
    if not found:
        raise SystemExit(f"Unknown task pack item: {args.item_id}")
    remaining = [item for item in data.get("items", []) if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    if not remaining and data.get("status") == "active":
        data["status"] = "completed"
    data.setdefault("mutation_log", []).append(
        {
            "timestamp": now_iso(),
            "action": "mark_consumed",
            "reason": args.reason or "pack item consumed by completed task",
            "item_id": args.item_id,
            "actor": "$derive-improvement-task",
        }
    )
    write_json(path, data)
    if args.render:
        render_path(path).write_text(render_markdown(root, path, data, args.language), encoding="utf-8")
    output = {"status": "ok", "pack_path": rel_path(root, path), "pack_id": data.get("pack_id"), "current_item_id": data.get("current_item_id")}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect and render orchestrate-task-cycle task pack queues.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status")
    status_p.add_argument("--format", choices=("json",), default="json")
    status_p.set_defaults(func=command_status)

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    validate_p.set_defaults(func=command_validate)

    render_p = sub.add_parser("render")
    render_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    render_p.add_argument("--language", default="ko", help="Markdown render language label.")
    render_p.set_defaults(func=command_render)

    next_p = sub.add_parser("next")
    next_p.set_defaults(func=command_next)

    consumed_p = sub.add_parser("mark-consumed")
    consumed_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack.")
    consumed_p.add_argument("--item-id", required=True)
    consumed_p.add_argument("--task-id")
    consumed_p.add_argument("--task-path")
    consumed_p.add_argument("--validation-verdict")
    consumed_p.add_argument("--progress-verdict")
    consumed_p.add_argument("--progress-kind")
    consumed_p.add_argument("--semantic-signature")
    consumed_p.add_argument("--blocker-signature")
    consumed_p.add_argument("--has-supplied-input-delta", action="store_true")
    consumed_p.add_argument("--supplied-input-artifact-path", action="append")
    consumed_p.add_argument("--reason")
    consumed_p.add_argument("--language", default="ko")
    consumed_p.add_argument("--render", action="store_true")
    consumed_p.set_defaults(func=command_mark_consumed)

    mutate_p = sub.add_parser("apply-mutation")
    mutate_p.add_argument("--plan", required=True, help="Mutation plan JSON path, inline JSON, or '-' for stdin.")
    mutate_p.add_argument("--action", help="Override action from the plan.")
    mutate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack or plan.pack_path.")
    mutate_p.add_argument("--language", default="ko")
    mutate_p.add_argument("--render", action="store_true")
    mutate_p.set_defaults(func=command_apply_mutation)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
