# @exegia/corpora-types

This package gives TypeScript names to the shared Corpora data shapes. A type
is like a checklist for an object: `Project` tells your editor which fields a
project has, while `ProjectStatus` lists its allowed status values. It contains
types only; it does not fetch data or convert books.

Generated TypeScript types for the Corpora apps suite. Do not edit: the
`.ts` files are produced by `corpora-typegen` from
`crates/corpora-core/schema/` and copied here by the `packages` workflow at
publish time.

## Install (GitHub Packages)

```sh
# .npmrc
@exegia:registry=https://npm.pkg.github.com

npm install @exegia/corpora-types
```

```ts
import type { Project, Corpus, ProjectStatus } from "@exegia/corpora-types"

function projectName(project: Pick<Project, "name">): string {
  return project.name
}
```

`Pick<Project, "name">` asks for just the `name` field in this example; a real
`Project` object needs all required fields. The source definitions live in the
[schema](../../crates/corpora-core/schema/README.md). To inspect or regenerate
the types locally, follow the [type generator](../../crates/corpora-typegen/README.md).
Generated files use TypeScript `camelCase` field names; JSON/Rust and SQL keep
the schema's `snake_case` names as described in the schema README.

Part of [corpora-core](https://github.com/exegia/corpora-core).
