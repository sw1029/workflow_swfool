from __future__ import annotations

import json

from orchestrate_task_cycle.stage.packet_projection import model_packet


def test_authority_model_packet_exposes_only_bounded_approval_ux_contract() -> None:
    config_sentinel = "raw-config-approval-body-must-not-survive"
    session_sentinel = "raw-session-approval-body-must-not-survive"
    full = {
        "config": {"approval_instructions": config_sentinel},
        "session": {"verbatim_user_statement": session_sentinel},
    }
    model = {
        "task": {"task_id": "task-approval-ux"},
        "goal_truth": {"used_goal_truth": []},
        "advice": {"items": []},
        "cycle": {"cycle_id": "cycle-approval-ux"},
        "selection_publication": None,
        "config": {"approval_instructions": config_sentinel},
        "session": {"verbatim_user_statement": session_sentinel},
    }

    packet = model_packet("authority", full, model, "normal")

    assert packet["approval_ux"] == {
        "prompt_gate": "manage-agent-authority:resolve.should_prompt",
        "reuse_system_next_action_first": True,
        "deduplicate_by": [
            "wait_identity",
            "effective_authority_fingerprint",
        ],
        "batch_only_exact_compatible_projections": True,
        "general_config_is_authority": False,
        "session_statement_is_authority": False,
        "reviewer_role": "optional_read_only_presentation",
    }
    assert "config" not in packet
    assert "session" not in packet
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    assert config_sentinel not in encoded
    assert session_sentinel not in encoded
