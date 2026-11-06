//! # corpora-core
//!
//! Core library for the Corpora project.
//!
//! ## Quick Start
//!
//! ```rust
//! use corpora_core::add;
//!
//! let result = add(2, 3);
//! assert_eq!(result, 5);
//! ```

mod error;

pub use error::Error;

/// A convenient Result type for this crate.
pub type Result<T> = std::result::Result<T, Error>;

/// Adds two numbers together.
///
/// # Examples
///
/// ```
/// use corpora_core::add;
///
/// assert_eq!(add(2, 3), 5);
/// assert_eq!(add(0, 0), 0);
/// ```
#[must_use]
pub const fn add(left: u64, right: u64) -> u64 {
    left + right
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_should_return_sum_of_two_numbers() {
        assert_eq!(add(2, 2), 4);
    }

    #[test]
    fn add_should_handle_zero() {
        assert_eq!(add(0, 5), 5);
        assert_eq!(add(5, 0), 5);
    }
}
