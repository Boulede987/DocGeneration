package com.shop.model;

public abstract class Entity {
    private long id;

    protected abstract void validate();

    public long id() {
        return id;
    }
}
