package com.shop.model;

import java.util.List;

/** A sellable item. Comments with { braces } must be ignored. */
public class Product extends Entity implements Comparable<Product>, Priced {
    public static final String DEFAULT_NAME = "unnamed {product}";
    private final String name;
    private Money price;
    protected List<Tag> tags;
    Category category;

    public Product(String name, Money price) {
        this.name = name;
        this.price = price;
    }

    @Override
    public Money price() {
        return price;
    }

    public void retag(Tag... newTags) {
        Tag first = newTags[0];
        tags = List.of(newTags);
    }

    @Override
    public int compareTo(Product other) {
        return name.compareTo(other.name);
    }
}
