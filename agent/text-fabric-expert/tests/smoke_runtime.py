"""Opt-in real TF/CF authoring, reload and MCP transport smoke test.

Run in an isolated environment with text-fabric and cfabric-mcp installed.
All dataset writes and runtime caches stay in temporary directories.
"""
import asyncio
import importlib.metadata
import json
from pathlib import Path
import shutil
import tempfile

from tf.fabric import Fabric
from cfabric.core import Fabric as ContextFabric
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify_mcp(root):
    command = shutil.which("cfabric-mcp")
    if command is None:
        raise RuntimeError("cfabric-mcp executable unavailable")
    params = StdioServerParameters(command=command, args=["--corpus", f"mini={root}"])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            assert {"list_corpora", "describe_corpus", "get_node_features"} <= tools
            for name, arguments in (
                ("list_corpora", {}),
                ("describe_corpus", {"corpus": "mini"}),
                ("get_node_features", {"corpus": "mini", "nodes": [1, 2],
                                       "features": ["word"]}),
            ):
                result = await session.call_tool(name, arguments)
                assert not result.isError, (name, result)
                if name == "get_node_features":
                    payload = result.model_dump_json()
                    assert "Alpha" in payload and "βήτα" in payload, payload
            return sorted(tools)


def main():
    with tempfile.TemporaryDirectory(prefix="tf-expert-smoke-") as temp:
        root = Path(temp) / "authored"
        root.mkdir()
        fabric = Fabric(locations=str(root), silent="deep")
        assert fabric.save(
            nodeFeatures={"otype": {1: "word", 2: "word", 3: "book", 4: "chapter", 5: "verse"},
                          "word": {1: "Alpha ", 2: "βήτα"}, "book": {3: "Mini"},
                          "chapter": {4: 1}, "verse": {5: 1}},
            edgeFeatures={"oslots": {3: {1, 2}, 4: {1, 2}, 5: {1, 2}}, "link": {1: {2: 7}}},
            metaData={"otype": {"valueType": "str"}, "oslots": {"valueType": "str"},
                      "word": {"valueType": "str"}, "book": {"valueType": "str"},
                      "chapter": {"valueType": "int"}, "verse": {"valueType": "int"},
                      "link": {"valueType": "int", "edgeValues": True},
                      "otext": {"fmt:text-orig-full": "{word}",
                                "sectionTypes": "book,chapter,verse",
                                "sectionFeatures": "book,chapter,verse"}},
        )
        receipts = {}
        for name, loader in (("text-fabric", Fabric), ("context-fabric", ContextFabric)):
            target = Path(temp) / name
            target.mkdir()
            for path in root.glob("*.tf"):
                shutil.copyfile(path, target / path.name)
            for phase in ("cold", "warm"):
                api = loader(locations=str(target), silent="deep").load("word book chapter verse link")
                assert api is not False
                assert api.T.text(3) == "Alpha βήτα"
                assert api.T.sectionFromNode(1) == ("Mini", 1, 1)
                assert tuple(api.E.link.f(1)) == ((2, 7),)
                receipts[f"{name}-{phase}"] = "passed"
        tools = asyncio.run(verify_mcp(root))
        print(json.dumps({"versions": {p: importlib.metadata.version(p) for p in
                                       ("text-fabric", "context-fabric", "cfabric-mcp")},
                          "loaders": receipts, "mcp_tools": tools}, indent=2))


if __name__ == "__main__":
    main()
