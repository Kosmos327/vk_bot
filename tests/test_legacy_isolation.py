from diagnostics import format_debug_status
from legacy_admin import (
    format_legacy_warning,
    is_legacy_admin_command,
    should_allow_legacy_admin_command,
)
from routing import is_legacy_confirm_command, is_legacy_discount_command
from scheduler import should_start_legacy_scheduler
from config import Config


def _cfg():
    return Config("t",1,10,"","https://example.com","token",True)


def test_is_legacy_admin_command_detection():
    assert is_legacy_admin_command('/admin')
    assert is_legacy_admin_command('/partners')
    assert is_legacy_admin_command('/approve 123')
    assert is_legacy_admin_command('/codes')
    assert is_legacy_admin_command('/checkcode ABC')
    assert is_legacy_admin_command('/usecode ABC')


def test_backend_mode_non_admin_cannot_use_legacy_admin_command():
    assert should_allow_legacy_admin_command(True, from_id=20, admin_id=10) is False


def test_backend_mode_admin_gets_legacy_warning():
    txt = format_legacy_warning('Legacy SQLite admin mode')
    assert 'Legacy SQLite admin command.' in txt


def test_legacy_client_aliases_do_not_map_to_legacy_admin_handler():
    assert is_legacy_discount_command('скидка 1')
    assert is_legacy_confirm_command('ДА 1')
    assert not is_legacy_admin_command('скидка 1')
    assert not is_legacy_admin_command('ДА 1')


def test_scheduler_disabled_in_backend_mode():
    assert should_start_legacy_scheduler(True) is False
    assert should_start_legacy_scheduler(False) is True


def test_debug_shows_legacy_flags_only():
    text = format_debug_status(_cfg(), user_state_size=0, legacy_admin_enabled=True, legacy_scheduler_enabled=False)
    assert 'legacy sqlite admin: enabled' in text
    assert 'legacy scheduler: disabled' in text
    assert 'database.db' not in text
