//! Keep the crate's distributable contract snapshots identical to the workspace sources.

use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

fn schema_names(directory: &Path) -> BTreeSet<String> {
    fs::read_dir(directory)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().into_string().unwrap())
        .filter(|name| name.ends_with(".schema.json"))
        .collect()
}

#[test]
fn packaged_contracts_match_canonical_sources() {
    let crate_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    let contracts = crate_dir.join("../../contracts");
    let assets = crate_dir.join("assets");

    assert_eq!(
        fs::read(assets.join("python/canonical_graph.py")).unwrap(),
        fs::read(contracts.join("python/canonical_graph.py")).unwrap()
    );

    let source_schemas = contracts.join("context-fabric/v1");
    let packaged_schemas = assets.join("context-fabric/v1");
    let names = schema_names(&source_schemas);
    assert_eq!(schema_names(&packaged_schemas), names);
    for name in names {
        assert_eq!(
            fs::read(packaged_schemas.join(&name)).unwrap(),
            fs::read(source_schemas.join(&name)).unwrap(),
            "{name} differs from its canonical source"
        );
    }
}
