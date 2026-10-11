use crate::model::product::{Priced, Product};
use crate::util::money::{Currency, Money};

impl Priced for Product {
    fn price(&self) -> Money {
        Money { cents: 0, currency: Currency::Eur }
    }
}

impl Product {
    pub fn discounted(&self, rate: u32) -> Money {
        self.price()
    }
}

impl Priced for u32 {
    fn price(&self) -> Money {
        Money { cents: *self as i64, currency: Currency::Usd }
    }
}
