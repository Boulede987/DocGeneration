package com.shop.model;

public enum Tag {
    NEW,
    SALE {
        @Override
        public String label() {
            return "on sale";
        }
    },
    LIMITED;

    public String label() {
        return name().toLowerCase();
    }
}
