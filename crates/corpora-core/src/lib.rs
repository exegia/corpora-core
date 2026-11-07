//! # corpora-core
//!
//! Core types and traits for the Corpora apps suite.
//!
//! This crate provides shared abstractions used across:
//! - Conversion runners
//! - Text-Fabric builder
//! - Model typings generation
//! - Data sources
//! - AI skills and agentic workflows

mod error;

pub use error::Error;

/// A convenient Result type for Corpora operations.
pub type Result<T> = std::result::Result<T, Error>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn error_conversion_should_create_conversion_error() {
        let err = Error::conversion("test error");
        assert!(matches!(err, Error::Conversion(_)));
    }

    #[test]
    fn error_config_should_create_config_error() {
        let err = Error::config("bad config");
        assert!(matches!(err, Error::Config(_)));
    }
}
