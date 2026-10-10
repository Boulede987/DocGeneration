package com.shop.model;

public record Money(long cents, Currency currency) {
    public static final Money ZERO = new Money(0, Currency.EUR);

    public Money plus(Money other) {
        return new Money(cents + other.cents, currency);
    }

    public enum Currency {
        EUR("€"), USD("$");

        private final String symbol;

        Currency(String symbol) {
            this.symbol = symbol;
        }
    }
}
