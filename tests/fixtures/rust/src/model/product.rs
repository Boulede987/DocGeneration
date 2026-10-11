use std::collections::HashMap;
use std::rc::{Rc, Weak};

use super::tag::Tag;
use crate::util::money::{Currency, Money};

/// Something with a description.
pub trait Describe {
    fn describe(&self) -> String;
}

pub trait Priced: Describe {
    fn price(&self) -> Money;
    fn currency(&self) -> Currency {
        self.price().currency
    }
}

#[derive(Debug, Clone)]
pub struct Product {
    pub name: String,
    price: Money,
    tags: Vec<Tag>,
    pub(crate) attributes: HashMap<String, String>,
    category: Option<Box<Category>>,
    marker: Rc<Marker>,
    pub(super) code: u32,
}

pub struct Category {
    pub label: String,
    parent: Option<Weak<Category>>,
    pub(self) secret: u8,
}

pub struct View<'a> {
    pub product: &'a Product,
}

pub struct Wrapper<T> {
    pub inner: T,
}

pub struct Sku(#[allow(dead_code)] pub u32, String);

pub struct Marker;

pub enum Status {
    Draft,
    Published { at: u64 },
    Archived(String),
    Tagged(Tag),
}

pub struct Hooks {
    pub on_change: fn(Tag) -> Sku,
    pub callback: Box<dyn Fn(Wrapper<u8>)>,
}

impl Product {
    pub const MAX_TAGS: usize = 8;

    pub fn new(name: &str, price: Money) -> Self {
        Product {
            name: name.to_string(),
            price,
            tags: Vec::new(),
            attributes: HashMap::new(),
            category: None,
            marker: Rc::new(Marker),
            code: 0,
        }
    }

    pub fn tag_count(&self) -> usize {
        self.tags.len()
    }

    fn rename(&mut self, name: String) {
        self.name = name;
    }
}

impl<T> Wrapper<T> {
    pub fn get(&self) -> &T {
        &self.inner
    }
}

impl Describe for Product {
    fn describe(&self) -> String {
        self.name.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::Product;
}
