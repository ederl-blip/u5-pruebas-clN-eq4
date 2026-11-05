from unittest.mock import Mock

import pytest

from src.application import OrderService
from src.domain import Order


def test_gateway_approved():
    gateway = Mock()
    gateway.charge.return_value = True
    assert OrderService(gateway).checkout(Order(100)) == 100
    gateway.charge.assert_called_once_with(100)

def test_gateway_rejected():
    gateway = Mock()
    gateway.charge.return_value = False
    with pytest.raises(RuntimeError):
        OrderService(gateway).checkout(Order(100))

def test_gateway_rejected_vip_200():
    gateway = Mock()
    gateway.charge.return_value = False                 # la pasarela rechaza
    with pytest.raises(RuntimeError, match="payment rejected"):
        OrderService(gateway).checkout(Order(200, vip=True))
    gateway.charge.assert_called_once_with(170)         # se intentó cobrar 170, una sola vez

def test_riesgo_pedido_confirmado_sin_pago():
    gateway = Mock()
    gateway.charge.return_value = False                  # la pasarela rechaza el pago
    order = Order(100)
    with pytest.raises(RuntimeError):
        OrderService(gateway).checkout(order)
    assert order.status == "CONFIRMED"   # riesgo conocido: quedó confirmado aunque el pago falló