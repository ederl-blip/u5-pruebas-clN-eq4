from dataclasses import dataclass


class CustomerHasDebt(Exception):
    pass

@dataclass
class Order:
    def _ensure_not_confirmed(self):
        if self.status == "CONFIRMED":
            raise ValueError("El pedido ya fue confirmado y no puede confirmarse de nuevo")
    total: float
    vip: bool = False
    status: str = "NEW"
    discount: float = 0.0

    def confirm(self, customer_debt=0):
        self._ensure_not_confirmed()
        if self.total <= 0:
            raise ValueError("El total del pedido debe ser mayor a cero")
        if customer_debt > 0:
            raise CustomerHasDebt("El cliente tiene un adeudo pendiente, por lo que no se puede confirmar el pedido")
        self.discount = round(self.total * 0.15, 2) if self.vip else 0.0
        self.status = "CONFIRMED"
        return self.total - self.discount
