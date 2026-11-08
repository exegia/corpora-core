# Source evidence and reuse map

Inspected 2026-11-06. Pins record research, not installed versions. Code was not
vendored. Dataset licensing remains separate. See sources.json for machine-readable evidence.

## Context-Fabric/context-fabric

Revision `86431a325cb627a1c736ff5d3f4c491d78bb8464`; license: MIT.
[libs/mcp/cfabric_mcp/tools.py](https://github.com/Context-Fabric/context-fabric/blob/86431a325cb627a1c736ff5d3f4c491d78bb8464/libs/mcp/cfabric_mcp/tools.py)

Primary runtime/MCP; inspected core 0.5.8 uses .cfm, MCP 0.1.8 separates total_count from cached_count. Fabric.save exists. search_csv can overwrite arbitrary paths: restrict or disable it.

## annotation/text-fabric

Revision `ffa490aa9b678b28c6defb6e3909b89a31bada42`; license: MIT.
[tf/convert/walker.py](https://github.com/annotation/text-fabric/blob/ffa490aa9b678b28c6defb6e3909b89a31bada42/tf/convert/walker.py)

Canonical format/runtime and CV.walk authoring. Check tf/core/data.py and tf/core/fabric.py for serialization/load/save semantics; inspected version 13.1.2.

## emmanuel-defreitas/metabook-py

Revision `e8347a46875890f40e728c02ffe825b6b78f78c8`; license: MIT.
[src/metabook_py/models/document.py](https://github.com/emmanuel-defreitas/metabook-py/blob/e8347a46875890f40e728c02ffe825b6b78f78c8/src/metabook_py/models/document.py)

Local checkout inspected: models/structure.py and mcp_server.py provide count/position structure validation and MCP analysis. No text in structural model. PDF adapter has no OCR.

## alexsosn/Agora

Revision `7f6bddf7810852b3039d1d7aa8fceeb5fde52e37`; license: MIT.
[plugins/context-fabric/src/agora_context_fabric/mcp_tools.py](https://github.com/alexsosn/Agora/blob/7f6bddf7810852b3039d1d7aa8fceeb5fde52e37/plugins/context-fabric/src/agora_context_fabric/mcp_tools.py)

Preferred managed plugin: discovery, source revisions, local import, lazy collection members, ordered overlays, load preflight, cancellation. Source-head features need not exist in published release.

## kungsik/kimsbible

Revision `cace895befed283c1ff0291f317a3ecf8e9bb042`; license: GPL-3.0.
[bhsheb_tfidf.py](https://github.com/kungsik/kimsbible/blob/cace895befed283c1ff0291f317a3ecf8e9bb042/bhsheb_tfidf.py)

Passage-based lexical analysis example; ETCBC-specific features and two-document TF-IDF are not general defaults.

## annotation/text-fabric-factory

Revision `bae4a39d298ab6a44668b37e565d799d11f9a244`; license: MIT.
[tff/convert/tei.py](https://github.com/annotation/text-fabric-factory/blob/bae4a39d298ab6a44668b37e565d799d11f9a244/tff/convert/tei.py)

Schema-aware TEI mixed-content walker and conversion phases; generic xml.py is an example and normalizes whitespace. Never execute untrusted hooks.

## ch-jensen/Text-Fabric-tutorials

Revision `b8578ddce0faf778ff10fed2e648c4d86adf422e`; license: not detected.
[Advanced Python and Text-Fabric.ipynb](https://github.com/ch-jensen/Text-Fabric-tutorials/blob/b8578ddce0faf778ff10fed2e648c4d86adf422e/Advanced%20Python%20and%20Text-Fabric.ipynb)

Teaching workflow for F/L/T traversal and aggregation. Link only; do not copy notebook code or hard-coded IDs.

## jcuenod/tftosql

Revision `21e8bd0100373aee633382f0ad87f32884f7447f`; license: not detected.
[main.py](https://github.com/jcuenod/tftosql/blob/21e8bd0100373aee633382f0ad87f32884f7447f/main.py)

Separate WordData/TreeData and preserve IDs. NULL collapsing is lossy; api_search.py SQL interpolation must not be reused.

## alexsosn/ontoTF

Revision `dadba070b93ef338681b87a04317826aa3b161e3`; license: MIT; OLiA CC BY 3.0.
[src/tfont/xml_mappings.py](https://github.com/alexsosn/ontoTF/blob/dadba070b93ef338681b87a04317826aa3b161e3/src/tfont/xml_mappings.py)

MappingCatalog resolves explicit correspondence dispositions. Current XML development differs from published v0.1.1. Ontology equivalence does not prove instance identity.

## jcuenod/biblecrawler-to-tf

Revision `a4307db428d8394415305a6c3c3d361d456910f6`; license: not detected.
[convert_to_tf.py](https://github.com/jcuenod/biblecrawler-to-tf/blob/a4307db428d8394415305a6c3c3d361d456910f6/convert_to_tf.py)

CSV annotation alignment and split/join cases. Reject ambiguous alignment instead of borrowing its mismatch fallback or dropping qere.

## adamb924/textfabric2sql

Revision `407222dca60a98bdc13ea0706c7571ba74cb1dcb`; license: not detected.
[tffile.cpp](https://github.com/adamb924/textfabric2sql/blob/407222dca60a98bdc13ea0706c7571ba74cb1dcb/tffile.cpp)

SQLite/MySQL export fixture ideas: ranges, implicit IDs, escaping, valued edges. Configuration export TODO means not lossless.

## tonyjurg/Doc4TF

Revision `7f7cbe5532d2add115ff6f4d503395299f19186f`; license: CC BY 4.0 per README.
[CreateFeatureDoc.ipynb](https://github.com/tonyjurg/Doc4TF/blob/7f7cbe5532d2add115ff6f4d503395299f19186f/CreateFeatureDoc.ipynb)

Feature metadata, per-node-type frequencies and explicit truncation. Parameterize corpus and inspect datatypes rather than assuming non-string means int.

## tonyjurg/TF_Knowledge_Graph

Revision `eb1947f15f35c8e77f75d88f53fcbb3affcb072c`; license: MIT.
[create_knowledge_graph.ipynb](https://github.com/tonyjurg/TF_Knowledge_Graph/blob/eb1947f15f35c8e77f75d88f53fcbb3affcb072c/create_knowledge_graph.ipynb)

Schema graph using namespaced feature/type keys. Observed applicability is not normative validity; this is not token graph export.

## jcuenod/tf_to_xml

Revision `75e89be5b2a41d43aab603d1acf7b86a89a2e273`; license: GPL-3.0.
[convert_tf_bhs_to_xml.ipynb](https://github.com/jcuenod/tf_to_xml/blob/75e89be5b2a41d43aab603d1acf7b86a89a2e273/convert_tf_bhs_to_xml.ipynb)

BHSA 2017-specific XML mapping with OSIS feature dependency. Not a generic reversible exporter.

## cbop-dev/tf-fast

Revision `c4cb4dd780e91d2216ad151c426e0e06021fb50e`; license: not detected.
[tffast/tfData/tfDataset.py](https://github.com/cbop-dev/tf-fast/blob/c4cb4dd780e91d2216ad151c426e0e06021fb50e/tffast/tfData/tfDataset.py)

Corpus adapter interfaces for text, references and lexemes. Biblical section assumptions require per-corpus adapters; do not vendor unlicensed code.

## saulocantanhede/tfgreek2

Revision `5b8da8c3106b7440a0467b6ec93e2c2ae6006d1c`; license: MIT code; check source data.
[programs/lowfat.py](https://github.com/saulocantanhede/tfgreek2/blob/5b8da8c3106b7440a0467b6ec93e2c2ae6006d1c/programs/lowfat.py)

Preserve XML attributes plus parent/sibling/subjref/frame edges through walker directors. Language-specific mapping, experimental corpus.

## pthu/tfbuilder

Revision `19f5982c95ae7453dfaa88b765b0215b896c8ed5`; license: Unlicense.
[tfbuilder/tfbuilder.py](https://github.com/pthu/tfbuilder/blob/19f5982c95ae7453dfaa88b765b0215b896c8ed5/tfbuilder/tfbuilder.py)

Legacy Csv2tf/Xml2tf directors with orig/post text features. Normalization and accent supply must be explicit policies; inspect compatibility before running.
