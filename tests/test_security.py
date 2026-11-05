from datetime import UTC, datetime, timedelta

from src.security import can_cancel


def test_owner_within_24h():
    now = datetime.now(UTC)
    assert can_cancel("NEW", 1, 1, False, now - timedelta(hours=1), now)

def test_stranger_denied():
    now = datetime.now(UTC)
    assert not can_cancel("NEW", 1, 2, False, now, now)

def test_shipped_denied_even_admin():
    now = datetime.now(UTC)
    assert not can_cancel("SHIPPED", 1, 1, True, now, now)

def test_expired_denied():
    now = datetime.now(UTC)
    assert not can_cancel("NEW", 1, 1, False, now - timedelta(hours=25), now)

FIXED_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def test_admin_cancels_new_order_of_another_user():
    created = FIXED_NOW - timedelta(hours=48)
    # dueño = 1, quien cancela = 99 (administrador), pedido NEW de 48 horas
    assert can_cancel("NEW", 1, 99, True, created, FIXED_NOW)


def test_owner_exactly_24h_denied():
    created = FIXED_NOW - timedelta(hours=24)
    # exactamente 24 horas: la regla exige "menos de 24 horas", así que se rechaza
    assert not can_cancel("NEW", 1, 1, False, created, FIXED_NOW)