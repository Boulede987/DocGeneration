pub mod model;
pub mod service;
pub mod util;

pub const VERSION: &str = "1.0";

pub fn version() -> &'static str {
    VERSION
}

pub fn tag_count() -> usize {
    Vec::<model::tag::Tag>::new().len()
}
