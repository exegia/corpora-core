//! Error types for the Corpora suite.

use thiserror::Error;

/// The error type for Corpora operations.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum Error {
    /// An I/O error occurred.
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// A conversion error occurred.
    #[error("conversion error: {0}")]
    Conversion(String),

    /// A configuration error occurred.
    #[error("configuration error: {0}")]
    Config(String),
}

impl Error {
    /// Creates a new conversion error.
    #[must_use]
    pub fn conversion(msg: impl Into<String>) -> Self {
        Self::Conversion(msg.into())
    }

    /// Creates a new configuration error.
    #[must_use]
    pub fn config(msg: impl Into<String>) -> Self {
        Self::Config(msg.into())
    }
}
