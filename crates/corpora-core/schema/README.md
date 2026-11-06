# Corpora schema

This directory is the **single source of truth** for the shared data model:

- `model.json` — version, config, scalars, enums and unions
- `domains/<name>.json` — one file per domain, holding its struct types

The `corpora-typegen` crate reads the directory and emits one file per
domain, plus barrels:

| Target     | Output                                           | Consumed by                    |
| ---------- | ------------------------------------------------ | ------------------------------ |
| Rust       | `generated/rust/{mod,enums,<domain>}.rs`         | corpora-core crates            |
| TypeScript | `generated/typescript/{index,enums,<domain>}.ts` | corpora-web and other TS apps  |
| SQL        | `generated/sql/schema.sql`                       | Postgres (Supabase) migrations |

SQL stays a single file because `CREATE TABLE` ordering follows foreign-key
dependencies across domains.

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

Hand-written SQL still has a place: _migrations_ evolving an existing
database belong in a migrations directory, with `generated/schema.sql` as the
authoritative description of the current shape.

## Format

`model.json`:

```jsonc
{
  "scalars": { "Uuid": { "rust": "uuid::Uuid", "typescript": "string", "sql": "UUID" } },
  "enums": { "ProjectStatus": { "values": ["draft", "..."] } },
  "unions": { "Node": { "variants": ["Section", "Block"] } },
}
```

`domains/platform.json` (one file per domain; the file stem is the domain name):

```jsonc
{
  "description": "Platform entities (Postgres tables).",
  "types": {
    "Project": {
      "table": "projects", // Postgres table (false = value object)
      "fields": {
        "id": { "type": "Uuid", "primary_key": true, "description": "..." },
        "creator_id": { "type": "Uuid", "references": "User.id" },
        "status": { "type": "ProjectStatus", "default": "draft" },
        "toc": { "type": "CorpusTocSection[]?", "sql_type": "JSONB" },
      },
    },
  },
}
```

Cross-domain references are allowed; emitters compute the `use` / `import`
lines per generated file.

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
