//! Schema definition model: the deserialized form of `schema/model.json`.

use std::collections::BTreeMap;

use serde::Deserialize;

/// Errors raised while loading or validating a schema.
#[derive(Debug, thiserror::Error)]
pub enum SchemaError {
    /// A schema file could not be read.
    #[error("reading schema: {0}")]
    Io(#[from] std::io::Error),
    /// The schema file could not be parsed as JSON.
    #[error("invalid schema JSON: {0}")]
    Parse(#[from] serde_json::Error),
    /// A field references a type that is not defined anywhere in the schema.
    #[error("unknown type `{type_name}` referenced by `{referrer}`")]
    UnknownType {
        /// The unresolved type name.
        type_name: String,
        /// The `Domain.Type.field` that referenced it.
        referrer: String,
    },
    /// A `references` target does not name an existing `Type.field`.
    #[error("unknown reference target `{target}` on `{referrer}`")]
    UnknownReference {
        /// The unresolved `Type.field` target.
        target: String,
        /// The `Domain.Type.field` that referenced it.
        referrer: String,
    },
}

/// The root schema document.
#[derive(Debug, Deserialize)]
pub struct Schema {
    /// Schema document version.
    pub version: String,
    /// Named scalar types with per-language mappings.
    #[serde(default)]
    pub scalars: BTreeMap<String, Scalar>,
    /// String enums shared across languages.
    #[serde(default)]
    pub enums: BTreeMap<String, EnumDef>,
    /// Tagged unions of struct types.
    #[serde(default)]
    pub unions: BTreeMap<String, UnionDef>,
    /// Types grouped by domain.
    #[serde(default)]
    pub domains: BTreeMap<String, Domain>,
}

/// A scalar type with its mapping in each target language.
#[derive(Debug, Deserialize)]
pub struct Scalar {
    /// Rust type path.
    pub rust: String,
    /// TypeScript type expression.
    pub typescript: String,
    /// SQL column type.
    pub sql: String,
    /// Human description.
    #[serde(default)]
    pub description: String,
}

/// A closed string enum.
#[derive(Debug, Deserialize)]
pub struct EnumDef {
    /// Human description.
    #[serde(default)]
    pub description: String,
    /// Allowed string values, in declaration order.
    pub values: Vec<String>,
}

/// A union (sum type) over previously defined struct types.
#[derive(Debug, Deserialize)]
pub struct UnionDef {
    /// Human description.
    #[serde(default)]
    pub description: String,
    /// Names of the member struct types.
    pub variants: Vec<String>,
}

/// A named group of related types.
#[derive(Debug, Deserialize)]
pub struct Domain {
    /// Human description of the domain.
    #[serde(default)]
    pub description: String,
    /// Struct types declared in this domain.
    pub types: BTreeMap<String, TypeDef>,
}

/// A struct type: either a database table or a value object.
#[derive(Debug, Deserialize)]
pub struct TypeDef {
    /// Human description.
    #[serde(default)]
    pub description: String,
    /// `false` for value objects, or the Postgres table name.
    #[serde(default)]
    pub table: TableSpec,
    /// Optional parent type whose fields are inherited.
    #[serde(default)]
    pub extends: Option<String>,
    /// Fields in declaration order.
    pub fields: serde_json::Map<String, serde_json::Value>,
}

impl TypeDef {
    /// Fields in declaration order, deserialized.
    pub fn fields(&self) -> impl Iterator<Item = (&str, FieldDef)> {
        self.fields.iter().filter_map(|(name, value)| {
            serde_json::from_value::<FieldDef>(value.clone())
                .ok()
                .map(|field| (name.as_str(), field))
        })
    }
}

/// Whether a type is backed by a Postgres table.
#[derive(Debug, Default)]
pub enum TableSpec {
    /// Value object: embedded in other types or serialized as JSONB.
    #[default]
    None,
    /// Backed by the named Postgres table.
    Named(String),
}

impl TableSpec {
    /// The table name, when present.
    pub fn name(&self) -> Option<&str> {
        match self {
            Self::None => None,
            Self::Named(name) => Some(name),
        }
    }
}

impl<'de> Deserialize<'de> for TableSpec {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        #[serde(untagged)]
        enum Raw {
            Flag(#[allow(dead_code)] bool),
            Name(String),
        }
        Ok(match Raw::deserialize(deserializer)? {
            Raw::Flag(_) => Self::None,
            Raw::Name(name) => Self::Named(name),
        })
    }
}

/// A single field of a struct type.
#[derive(Debug, Deserialize)]
pub struct FieldDef {
    /// Type expression: `T`, `T?`, `T[]`, `T[]?` or `Map<K, V>`.
    #[serde(rename = "type")]
    pub ty: String,
    /// Human description.
    #[serde(default)]
    pub description: String,
    /// Part of the primary key.
    #[serde(default)]
    pub primary_key: bool,
    /// Carries a UNIQUE constraint.
    #[serde(default)]
    pub unique: bool,
    /// Foreign key target as `Type.field`.
    #[serde(default)]
    pub references: Option<String>,
    /// Default value literal.
    #[serde(default)]
    pub default: Option<serde_json::Value>,
    /// Override for the generated SQL column type.
    #[serde(default)]
    pub sql_type: Option<String>,
}

/// A parsed field type expression.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FieldType {
    /// A named scalar, enum, union or struct type.
    Named(String),
    /// `T?`
    Optional(Box<Self>),
    /// `T[]`
    List(Box<Self>),
    /// `Map<K, V>`
    Map(Box<Self>, Box<Self>),
}

impl FieldType {
    /// Parse a type expression such as `String`, `Uuid?`, `Property[]`,
    /// `CorpusTocSection[]?` or `Map<String, i64>`.
    pub fn parse(expr: &str) -> Self {
        let expr = expr.trim();
        if let Some(inner) = expr.strip_suffix('?') {
            return Self::Optional(Box::new(Self::parse(inner)));
        }
        if let Some(inner) = expr.strip_suffix("[]") {
            return Self::List(Box::new(Self::parse(inner)));
        }
        if let Some(args) = expr.strip_prefix("Map<").and_then(|s| s.strip_suffix('>')) {
            if let Some((key, value)) = args.split_once(',') {
                return Self::Map(Box::new(Self::parse(key)), Box::new(Self::parse(value)));
            }
        }
        Self::Named(expr.to_owned())
    }

    /// The innermost named types of the expression.
    pub fn named(&self) -> Vec<&str> {
        match self {
            Self::Named(name) => vec![name],
            Self::Optional(inner) | Self::List(inner) => inner.named(),
            Self::Map(key, value) => {
                let mut names = key.named();
                names.extend(value.named());
                names
            }
        }
    }
}

/// Where a named type is declared, used by emitters to compute imports.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TypeHome<'schema> {
    /// A Rust primitive permitted in field expressions.
    Primitive,
    /// Declared under `scalars`.
    Scalar,
    /// Declared under `enums`.
    Enum,
    /// A union, homed in the domain of its first variant.
    Union(&'schema str),
    /// A struct type declared in the named domain.
    Struct(&'schema str),
}

impl Schema {
    /// Load and validate a schema from JSON text.
    pub fn from_json(json: &str) -> Result<Self, SchemaError> {
        let schema: Self = serde_json::from_str(json)?;
        schema.validate()?;
        Ok(schema)
    }

    /// Load and validate a schema from a directory containing `model.json`
    /// (version, config, scalars, enums, unions) and `domains/<name>.json`.
    pub fn from_dir(dir: &std::path::Path) -> Result<Self, SchemaError> {
        let root = std::fs::read_to_string(dir.join("model.json"))?;
        let mut schema: Self = serde_json::from_str(&root)?;
        let mut entries: Vec<std::path::PathBuf> = std::fs::read_dir(dir.join("domains"))?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
            .collect();
        entries.sort();
        for path in entries {
            let name = path
                .file_stem()
                .map(|stem| stem.to_string_lossy().into_owned())
                .unwrap_or_default();
            let json = std::fs::read_to_string(&path)?;
            let domain: Domain = serde_json::from_str(&json)?;
            schema.domains.insert(name, domain);
        }
        schema.validate()?;
        Ok(schema)
    }

    /// Where the named type is declared.
    pub fn type_home(&self, name: &str) -> Option<TypeHome<'_>> {
        const PRIMITIVES: &[&str] = &["String", "bool", "i32", "i64", "u32", "u64", "f32", "f64"];
        if PRIMITIVES.contains(&name) {
            return Some(TypeHome::Primitive);
        }
        if self.scalars.contains_key(name) {
            return Some(TypeHome::Scalar);
        }
        if self.enums.contains_key(name) {
            return Some(TypeHome::Enum);
        }
        if let Some(union) = self.unions.get(name) {
            let first = union.variants.first()?;
            return self.domain_of(first).map(TypeHome::Union);
        }
        self.domain_of(name).map(TypeHome::Struct)
    }

    /// The domain in which a struct type is declared.
    fn domain_of(&self, type_name: &str) -> Option<&str> {
        self.domains.iter().find_map(|(domain_name, domain)| {
            domain
                .types
                .contains_key(type_name)
                .then_some(domain_name.as_str())
        })
    }

    /// Every type name declared in the schema (scalars, enums, unions, structs)
    /// plus the Rust primitives permitted in field expressions.
    fn known_types(&self) -> Vec<&str> {
        const PRIMITIVES: &[&str] = &["String", "bool", "i32", "i64", "u32", "u64", "f32", "f64"];
        let mut names: Vec<&str> = PRIMITIVES.to_vec();
        names.extend(self.scalars.keys().map(String::as_str));
        names.extend(self.enums.keys().map(String::as_str));
        names.extend(self.unions.keys().map(String::as_str));
        for domain in self.domains.values() {
            names.extend(domain.types.keys().map(String::as_str));
        }
        names
    }

    /// Look up a struct type by name across all domains.
    pub fn find_type(&self, name: &str) -> Option<(&str, &TypeDef)> {
        self.domains.values().find_map(|domain| {
            domain
                .types
                .get_key_value(name)
                .map(|(key, def)| (key.as_str(), def))
        })
    }

    fn validate(&self) -> Result<(), SchemaError> {
        let known = self.known_types();
        for (domain_name, domain) in &self.domains {
            for (type_name, type_def) in &domain.types {
                for (field_name, field) in type_def.fields() {
                    let referrer = format!("{domain_name}.{type_name}.{field_name}");
                    for named in FieldType::parse(&field.ty).named() {
                        if !known.contains(&named) {
                            return Err(SchemaError::UnknownType {
                                type_name: named.to_owned(),
                                referrer,
                            });
                        }
                    }
                    if let Some(target) = &field.references {
                        let target_type = target.split('.').next().unwrap_or(target);
                        if self.find_type(target_type).is_none() {
                            return Err(SchemaError::UnknownReference {
                                target: target.clone(),
                                referrer,
                            });
                        }
                    }
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_should_handle_optional_list() {
        let ty = FieldType::parse("CorpusTocSection[]?");
        assert_eq!(
            ty,
            FieldType::Optional(Box::new(FieldType::List(Box::new(FieldType::Named(
                "CorpusTocSection".to_owned()
            )))))
        );
    }

    #[test]
    fn parse_should_handle_map() {
        let ty = FieldType::parse("Map<String, i64>");
        assert_eq!(
            ty,
            FieldType::Map(
                Box::new(FieldType::Named("String".to_owned())),
                Box::new(FieldType::Named("i64".to_owned()))
            )
        );
    }

    #[test]
    fn from_json_should_reject_unknown_type() {
        let json = r#"{
            "version": "1.0.0",
            "domains": {
                "d": { "types": { "T": { "fields": {
                    "x": { "type": "Nope" }
                } } } }
            }
        }"#;
        let err = Schema::from_json(json).unwrap_err();
        assert!(matches!(err, SchemaError::UnknownType { .. }));
    }
}
