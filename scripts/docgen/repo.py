"""Read facts out of the JourneyMesh repository.

Everything the guide states about dependencies, files, tables and environment
variables comes from here, so the document describes the repository as it
actually is rather than as it was imagined.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


@dataclass
class Facts:
    python_packages: list[tuple[str, str]] = field(default_factory=list)
    node_deps: list[tuple[str, str]] = field(default_factory=list)
    node_dev_deps: list[tuple[str, str]] = field(default_factory=list)
    backend_env: list[str] = field(default_factory=list)
    backend_files: int = 0
    frontend_files: int = 0
    backend_test_files: list[str] = field(default_factory=list)
    backend_test_count: int = 0
    frontend_test_files: list[str] = field(default_factory=list)
    locale_keys: int = 0
    tables: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    graph_nodes: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    eval_cases: list[str] = field(default_factory=list)
    api_routes: list[tuple[str, str]] = field(default_factory=list)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def collect() -> Facts:
    facts = Facts()

    # ---- Python dependencies ------------------------------------------
    for line in _read(BACKEND / "requirements.txt").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-\[\]]+)\s*([<>=!~].*)?$", line)
        if match:
            facts.python_packages.append((match.group(1), (match.group(2) or "").strip()))

    # ---- Node dependencies --------------------------------------------
    package_json = _read(FRONTEND / "package.json")
    if package_json:
        data = json.loads(package_json)
        facts.node_deps = sorted(data.get("dependencies", {}).items())
        facts.node_dev_deps = sorted(data.get("devDependencies", {}).items())

    # ---- Environment variables ----------------------------------------
    for line in _read(BACKEND / ".env.example").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            facts.backend_env.append(line.split("=", 1)[0].strip())

    # ---- File inventory ------------------------------------------------
    facts.backend_files = len(
        [p for p in (BACKEND / "app").rglob("*.py") if "__pycache__" not in str(p)]
    )
    facts.frontend_files = len(
        [p for p in (FRONTEND / "src").rglob("*.ts*") if p.suffix in {".ts", ".tsx"}]
    )

    facts.backend_test_files = sorted(p.name for p in (BACKEND / "tests").glob("test_*.py"))
    for path in (BACKEND / "tests").glob("test_*.py"):
        facts.backend_test_count += len(re.findall(r"^def test_|^async def test_",
                                                   _read(path), re.M))
    facts.frontend_test_files = sorted(
        p.name for p in (FRONTEND / "src" / "test").glob("*.test.*")
    )

    # ---- i18n ----------------------------------------------------------
    locales = _read(FRONTEND / "src" / "locales" / "en" / "common.json")
    if locales:
        def count(node) -> int:
            if isinstance(node, dict):
                return sum(count(value) for value in node.values())
            return 1
        facts.locale_keys = count(json.loads(locales))

    # ---- Database tables ------------------------------------------------
    facts.tables = re.findall(r'__tablename__ = "(\w+)"', _read(BACKEND / "app" / "db" / "models.py"))

    # ---- Agents, nodes, tools -------------------------------------------
    facts.agents = sorted(
        p.stem for p in (BACKEND / "app" / "agents").glob("*.py")
        if p.stem not in {"__init__", "base"}
    )
    facts.graph_nodes = re.findall(
        r'builder\.add_node\("(\w+)"', _read(BACKEND / "app" / "graph" / "travel_graph.py")
    )
    facts.tools = re.findall(r'^\s{4}"(\w+)": \{', _read(BACKEND / "app" / "guardrails" / "policies.py"), re.M)

    # ---- CI/CD -----------------------------------------------------------
    facts.workflows = sorted(p.name for p in (ROOT / ".github" / "workflows").glob("*.yml"))

    # ---- Evaluation cases -------------------------------------------------
    cases = _read(BACKEND / "evals" / "cases.json")
    if cases:
        facts.eval_cases = [case["id"] for case in json.loads(cases)["cases"]]

    # ---- API routes -------------------------------------------------------
    for path in (BACKEND / "app" / "api" / "routes").glob("*.py"):
        source = _read(path)
        prefix = re.search(r'APIRouter\(prefix="([^"]*)"', source)
        base = prefix.group(1) if prefix else ""
        for method, route in re.findall(r'@router\.(get|post|delete|put)\(\s*"([^"]*)"', source):
            facts.api_routes.append((method.upper(), f"/api/v1{base}{route}"))
    facts.api_routes.sort(key=lambda item: item[1])

    return facts


FACTS = collect()
