#!/usr/bin/env python3
"""Generate docs/JourneyMesh_Architecture_Explanation_Guide.docx.

The document is built from the repository itself: dependency lists, database
tables, graph nodes, agent names, tool policies, API routes, environment
variables, translation keys and test counts are read from the source at
generation time rather than transcribed, so the guide cannot silently drift
from the code it describes.

Usage:
    python scripts/generate_architecture_doc.py [--output PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from docgen.builder import DocumentMeta, Guide  # noqa: E402
from docgen import (  # noqa: E402
    part1_foundations,
    part2_graph,
    part3_mcp,
    part4_backend,
    part5_frontend,
    part6_data,
    part7_quality,
    part8_deploy,
    part9_decisions,
    part10_operations,
    part11_interview,
    part12_academic,
    part13_reference,
)

DEFAULT_OUTPUT = ROOT / "docs" / "JourneyMesh_Architecture_Explanation_Guide.docx"

PARTS = (
    part1_foundations,
    part2_graph,
    part3_mcp,
    part4_backend,
    part5_frontend,
    part6_data,
    part7_quality,
    part8_deploy,
    part9_decisions,
    part10_operations,
    part11_interview,
    part12_academic,
    part13_reference,
)

META = DocumentMeta(
    title="JourneyMesh\nArchitecture Explanation Guide",
    subtitle=(
        "A complete technical, operational and academic explanation of a "
        "multilingual multi-agent travel planning system - its architecture, "
        "its agents, its guardrails, its evaluation, its deployment and the "
        "reasoning behind every decision."
    ),
    project="JourneyMesh",
    tagline="Every journey, intelligently connected.",
    author="Pankaj Pramanik",
    email="pkp2.me2k9@gmail.com",
    website="https://pankajpramanik.com",
    version="1.0",
)


def build(output: Path) -> Guide:
    guide = Guide(META)
    guide.cover()
    guide.table_of_contents()
    for part in PARTS:
        part.write(guide)
    guide.add_page_furniture()
    output.parent.mkdir(parents=True, exist_ok=True)
    guide.save(str(output))
    return guide


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    guide = build(args.output)
    size_kb = args.output.stat().st_size / 1024
    print(f"wrote {args.output.relative_to(ROOT)}")
    print(f"  {size_kb:.0f} KB, {guide.table_count} tables, {guide.figure_count} figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
