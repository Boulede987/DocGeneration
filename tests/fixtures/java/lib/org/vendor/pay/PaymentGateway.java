package org.vendor.pay;

public interface PaymentGateway {
    boolean charge(long cents);
}
