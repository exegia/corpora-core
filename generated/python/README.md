# Corpora schema types for Python

This package is generated from `crates/corpora-core/schema`. Install it from
this directory, or pin the `generated/python` subdirectory of a core commit.
Its package version follows the schema version. Run `make types` after editing
the schema and `make types-check` before committing.

The first reviewed value object is `TextRange`, serialized as
`{"start": 1, "end": 2}`. Its offsets count Unicode scalars. Both offsets
must fit `u32`; this schema does not currently assert `start <= end` or a
particular text length. Unknown input fields are ignored, matching Rust serde.
The separate `corpora-model` binding represents its
own `TextRange` as a JSON pair and checks ordering. Convert explicitly between
the two wire contracts rather than treating them as interchangeable.

HTTP request and response wrappers remain in `corpora-api`; generated types
contain only shared domain values.
