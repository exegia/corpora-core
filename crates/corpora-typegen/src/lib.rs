//! Generates Rust, TypeScript, Swift, Python and SQL types from the Corpora schema definition.
//!
//! The schema lives at `crates/corpora-core/schema/model.json` and is the
//! single source of truth for every generated artifact:
//!
//! - **Rust**: structs and enums with serde derives ([`rust::emit`]).
//! - **TypeScript**: interfaces and string-literal unions ([`typescript::emit`]).
//! - **Swift**: `Codable` structs and enums ([`swift::emit`]).
//! - **Python**: reviewed value objects for API use ([`python::emit`]).
//! - **SQL**: Postgres `CREATE TABLE` DDL for table-backed types ([`sql::emit`]).

pub mod python;
pub mod rust;
pub mod schema;
pub mod sql;
pub mod swift;
pub mod typescript;

pub use schema::{Schema, SchemaError};
