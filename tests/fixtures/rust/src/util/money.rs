#[derive(Clone, Copy, Debug)]
pub enum Currency {
    Eur,
    Usd,
}

#[derive(Clone, Debug)]
pub struct Money {
    pub cents: i64,
    pub currency: Currency,
}

pub fn zero() -> Money {
    Money { cents: 0, currency: Currency::Eur }
}
