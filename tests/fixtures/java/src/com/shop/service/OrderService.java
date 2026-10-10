package com.shop.service;

import com.shop.model.Category.Path;
import com.shop.model.Money;
import com.shop.model.Product;
import com.shop.util.Repository;
import java.util.Map;
import java.util.HashMap;
import org.vendor.pay.PaymentGateway;

public class OrderService extends BaseService implements AutoCloseable {
    private final Repository<Product> products;
    public final Map<String, Order> ordersById = new HashMap<>();
    private PaymentGateway gateway;

    public OrderService(Repository<Product> products) {
        this.products = products;
    }

    public Order place(Product product, int quantity) {
        Money total = product.price();
        Order order = new Order(product, quantity, total);
        ordersById.put(order.id(), order);
        return order;
    }

    Path categoryPathOf(Product product) {
        return null;
    }

    @Override
    public void close() {
    }

    public record Order(Product product, int quantity, Money total) {
        public String id() {
            return product.toString() + quantity;
        }
    }
}
