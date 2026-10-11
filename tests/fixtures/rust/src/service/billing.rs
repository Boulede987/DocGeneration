use crate::util::pricing::total;

pub struct Billing;

impl Billing {
    pub fn local(total: u32) -> u32 {
        let doubled = total * 2;
        doubled
    }
}
