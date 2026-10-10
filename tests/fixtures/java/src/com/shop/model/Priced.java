package com.shop.model;

public interface Priced {
    int MAX_DISCOUNT_PERCENT = 50;

    Money price();

    default boolean isFree() {
        return price().cents() == 0;
    }

    static Priced of(Money money) {
        return () -> money;
    }
}
