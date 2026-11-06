# corpora-core

Core types and traits for the Corpora apps suite.

## Overview

This crate provides shared abstractions used across:
- Conversion runners
- Text-Fabric builder  
- Model typings generation
- Data sources
- AI skills and agentic workflows

## Usage

```rust
use corpora_core::{Error, Result};

fn process_document() -> Result<()> {
    // Your processing logic here
    Ok(())
}
```

## Features

- `serde` - Enable serialization support for core types

## License

MIT OR Apache-2.0
