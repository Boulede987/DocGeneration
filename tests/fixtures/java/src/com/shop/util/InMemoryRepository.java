package com.shop.util;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class InMemoryRepository<T> implements Repository<T> {
    private final List<T> items = new ArrayList<>();
    private static int instances;

    @Override
    public Optional<T> find(long id) {
        return Optional.empty();
    }

    @Override
    public List<T> all() {
        return items;
    }

    @Override
    public void save(T item) {
        items.add(item);
        Counter.increment();
    }

    static final class Counter {
        private static int count;

        static void increment() {
            count++;
        }
    }
}
