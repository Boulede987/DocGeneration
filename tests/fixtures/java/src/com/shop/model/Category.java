package com.shop.model;

import java.util.ArrayList;
import java.util.List;

public class Category {
    private final List<Product> products = new ArrayList<>();
    private Category parent;

    public static class Path {
        private final String[] segments;

        Path(String[] segments) {
            this.segments = segments;
        }
    }

    public Path path() {
        return new Path(new String[0]);
    }
}
