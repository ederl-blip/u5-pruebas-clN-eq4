class OrderService:
    def __init__(self, gateway):
        self.gateway = gateway

    def checkout(self, order):
        amount = order.confirm()
        if not self.gateway.charge(amount):
            raise RuntimeError("El pago fue rechazado. Intenta con otro método de pago")
        return amount
