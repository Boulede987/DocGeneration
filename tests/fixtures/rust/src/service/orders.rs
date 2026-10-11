use crate::model::{product::{Priced as PricedItem, Product}, tag::Tag};
use crate::util::{self, pricing::DEFAULT_RATE as _};
use self::drafts::Draft;
use crate::util::money::*;
use crate::util::pricing;

pub trait Repository {
    fn find(&self, key: &str) -> Option<Product>;
}

pub struct OrderService {
    products: Vec<Product>,
    repository: Box<dyn Repository>,
    labels: Vec<Tag>,
    draft: Option<Draft>,
    fallback: util::money::Currency,
}

impl OrderService {
    pub fn total(&self) -> Money {
        pricing::total(&self.products)
    }

    pub fn rate() -> u32 {
        crate::util::pricing::DEFAULT_RATE
    }

    pub fn best(&self, items: Vec<Box<dyn PricedItem>>) -> Option<Product> {
        None
    }

    pub fn category(&self) -> Option<crate::model::product::Category> {
        None
    }

    pub fn empty() -> Money {
        zero()
    }
}

mod drafts {
    use super::Repository;

    pub struct Draft {
        pub id: u32,
        source: Option<Box<dyn Repository>>,
    }
}

#[cfg(test)]
// Test helpers.
mod tests {
    struct TestOnly;

    #[test]
    fn it_works() {}
}

#[cfg(all(test, feature = "slow"))]
mod slow_tests {
    struct SlowOnly;
}
