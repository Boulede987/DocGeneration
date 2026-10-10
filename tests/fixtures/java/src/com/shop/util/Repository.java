package com.shop.util;

import java.util.List;
import java.util.Optional;

public interface Repository<T> {
    Optional<T> find(long id);

    List<T> all();

    void save(T item);
}
