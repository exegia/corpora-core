//! Error types for corpora-core.

use thiserror::Error;

/// The error type for corpora-core operations.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum Error {
    /// An I/O error occurred.
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// A generic error with a message.
    #[error("{0}")]
    Message(String),
}

impl Error {
    /// Creates a new error with the given message.
    #[must_use]
    pub fn message(msg: impl Into<String>) -> Self {
        Self::Message(msg.into())
    }
}
