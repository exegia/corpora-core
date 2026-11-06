# Corpora schema

`model.json` is the **single source of truth** for the shared data model. The
`corpora-typegen` crate reads it and emits:

| Target     | Output                 | Consumed by                              |
| ---------- | ---------------------- | ---------------------------------------- |
| Rust       | `generated/types.rs`   | corpora-core crates                      |
| TypeScript | `generated/types.ts`   | corpora-web and other TS apps            |
| SQL        | `generated/schema.sql` | Postgres (Supabase) migrations           |

Regenerate after editing the schema:

```sh
cargo run -p corpora-typegen
```

## Why JSON source, generated SQL (not `.sql` source files)

- **One format, three targets.** Relationships, optionality and docs are
  declared once; the SQL emitter derives `NOT NULL`, `REFERENCES`, `CHECK`
  and `PRIMARY KEY` from the same declarations that produce Rust `Option<T>`
  and TypeScript `| null`. Hand-written `.sql` would have to be re-parsed to
  get the other two languages, and SQL carries too little type information
  (no unions, no value objects, no per-language scalar mappings).
- **Value objects vs tables are explicit.** `"table": "<name>"` makes a type a
  Postgres table; `"table": false` keeps it a serialized value object (stored
  as `JSONB` when embedded in a table). SQL cannot express that distinction.
- **Enums as CHECK constraints.** Enums emit `TEXT ... CHECK (col IN (...))`
  rather than `CREATE TYPE`, so adding a value is an additive migration.

Hand-written SQL still has a place: *migrations* evolving an existing
database belong in a migrations directory, with `generated/schema.sql` as the
authoritative description of the current shape.

## Format

```jsonc
{
  "scalars": { "Uuid": { "rust": "uuid::Uuid", "typescript": "string", "sql": "UUID" } },
  "enums":   { "ProjectStatus": { "values": ["draft", "..."] } },
  "unions":  { "Node": { "variants": ["Section", "Block"] } },
  "domains": {
    "platform": {
      "types": {
        "Project": {
          "table": "projects",            // Postgres table (false = value object)
          "fields": {
            "id":         { "type": "Uuid", "primary_key": true, "description": "..." },
            "creator_id": { "type": "Uuid", "references": "User.id" },
            "status":     { "type": "ProjectStatus", "default": "draft" },
            "toc":        { "type": "CorpusTocSection[]?", "sql_type": "JSONB" }
          }
        }
      }
    }
  }
}
```

Field type syntax: `T` required, `T?` optional, `T[]` list, `T[]?` optional
list, `Map<K, V>` map. Field names are `snake_case` in the schema; the
TypeScript emitter converts them to `camelCase`, SQL keeps them as columns.

## Domains

- **document** — canonical document model (serialization format, no tables).
- **platform** — users, organizations, projects, corpus documents (tables).
- **license** — licence catalog and project attachments (tables).
- **conversion** — corpora-py conversion pipeline contract (wire types).
- **explore** — corpus exploration API contract (wire types).

Platform, license and conversion types mirror
[`corpora-web`](https://github.com/exegia/corpora-web) `app/lib/**/types.ts`;
keep the two in sync when the web app's model changes.
