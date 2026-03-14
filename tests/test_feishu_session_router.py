"""Unit tests for Feishu session router state and command handling."""

from __future__ import annotations

from pathlib import Path

from atom_agent.channels.feishu_session import (
    FeishuSessionRouter,
    make_chitchat_session_key,
    make_normal_session_key,
)


def test_router_handles_normal_session_commands_and_persists_state(tmp_path: Path) -> None:
    router = FeishuSessionRouter(workspace=tmp_path)
    chat_id = "oc_chat_1"

    base_key = router.get_active_normal_session_key(chat_id)
    assert base_key == make_normal_session_key(chat_id)

    new_result = router.handle_command(chat_id, "/new")
    assert new_result is not None
    assert new_result.metadata["feishu_new_session"] is True
    assert new_result.session_key != base_key
    assert router.get_active_normal_session_key(chat_id) == new_result.session_key

    session_id = str(new_result.metadata["feishu_session_id"])
    resume_result = router.handle_command(chat_id, f"/resume {session_id}")
    assert resume_result is not None
    assert resume_result.metadata["feishu_resume_ok"] is True
    assert resume_result.session_key == new_result.session_key

    revert_result = router.handle_command(chat_id, "/resume default")
    assert revert_result is not None
    assert revert_result.metadata["feishu_resume_ok"] is True
    assert revert_result.session_key == base_key

    # Reload to confirm persisted session state survives process restart.
    router_reloaded = FeishuSessionRouter(workspace=tmp_path)
    assert router_reloaded.get_active_normal_session_key(chat_id) == base_key
    known = router_reloaded.list_normal_session_ids(chat_id)
    assert "default" in known
    assert session_id in known


def test_router_chitchat_commands_switch_routing_and_alias(tmp_path: Path) -> None:
    router = FeishuSessionRouter(workspace=tmp_path)
    chat_id = "oc_chat_2"

    assert router.is_in_chitchat(chat_id) is False
    assert router.get_session_key(chat_id) == make_normal_session_key(chat_id)

    on_result = router.handle_command(chat_id, "/chitchat_on")
    assert on_result is not None
    assert on_result.metadata["chitchat_turned_on"] is True
    assert router.is_in_chitchat(chat_id) is True
    assert router.get_session_key(chat_id) == make_chitchat_session_key(chat_id)

    off_alias = router.handle_command(chat_id, "/next_time")
    assert off_alias is not None
    assert off_alias.metadata["feishu_next_time_alias"] is True
    assert router.is_in_chitchat(chat_id) is False
    assert router.get_session_key(chat_id) == make_normal_session_key(chat_id)


def test_router_resume_rejects_unknown_session(tmp_path: Path) -> None:
    router = FeishuSessionRouter(workspace=tmp_path)
    result = router.handle_command("oc_chat_3", "/resume missing")
    assert result is not None
    assert result.metadata["feishu_resume_ok"] is False
    assert "Session not found" in str(result.metadata["feishu_resume_error"])
