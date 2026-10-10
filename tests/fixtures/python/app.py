from shop.service.orders import OrderService


class App:
    def __init__(self, service: OrderService):
        self._service = service

    def run(self) -> None:
        print(self._service)
