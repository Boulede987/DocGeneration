use super::money::{Currency, Money};
use crate::model::product::Product;

pub const DEFAULT_RATE: u32 = 20;
static mut COUNTER: u32 = 0;

pub fn total(products: &[Product]) -> Money {
    let cents = products.len() as i64;
    Money { cents: round(cents), currency: Currency::Eur }
}

fn round(amount: i64) -> i64 {
    amount
}
