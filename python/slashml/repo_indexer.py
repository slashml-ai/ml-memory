"""Repository Code Indexer & Behavioral / Bug Search Client for `/ ml` (`https://api.slashml.ai`).

Scans source files locally and dispatches AST/symbol chunks and queries to the
`/ ml` Cloud API (`https://api.slashml.ai`).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from slashml.client import MemoryClient

SUPPORTED_CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}
EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "upstream",
    "experiments",
    "corpus",
    "results",
    "vendor",
    "third_party",
    "coverage",
    ".next",
    ".nuxt",
    ".wrangler",
    "site",
    "artifacts",
    "tmp",
    "temp",
    "logs",
}


class RepositoryIndexer:
    """Indexes repository source files into `/ ml` Cloud (`https://api.slashml.ai`)."""

    def __init__(
        self,
        client: MemoryClient,
        *,
        user_id: str = "repo",
        namespace: str = "default",
    ) -> None:
        self.client = client
        self.user_id = user_id
        self.namespace = namespace

    def _extract_python_chunks(self, rel_path: str, source: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        lines = source.splitlines()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return [
                {
                    "id": f"code::{rel_path}::file",
                    "text": f"# File: {rel_path}\n{source[:4000]}",
                    "user_id": self.user_id,
                    "metadata": {
                        "modality": "code",
                        "language": "python",
                        "file_path": rel_path,
                        "symbol_name": Path(rel_path).stem,
                        "symbol_kind": "module",
                        "start_line": 1,
                        "end_line": len(lines),
                    },
                }
            ]

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = getattr(node, "lineno", 1)
                end = getattr(node, "end_lineno", start)
                snippet = "\n".join(lines[start - 1 : end])
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                chunks.append(
                    {
                        "id": f"code::{rel_path}::{node.name}:{start}",
                        "text": f"# File: {rel_path}:{start}-{end} ({kind} {node.name})\n{snippet}",
                        "user_id": self.user_id,
                        "metadata": {
                            "modality": "code",
                            "language": "python",
                            "file_path": rel_path,
                            "symbol_name": node.name,
                            "symbol_kind": kind,
                            "start_line": start,
                            "end_line": end,
                        },
                    }
                )
        if not chunks and source.strip():
            chunks.append(
                {
                    "id": f"code::{rel_path}::module",
                    "text": f"# File: {rel_path}\n{source[:4000]}",
                    "user_id": self.user_id,
                    "metadata": {
                        "modality": "code",
                        "language": "python",
                        "file_path": rel_path,
                        "symbol_name": Path(rel_path).stem,
                        "symbol_kind": "module",
                        "start_line": 1,
                        "end_line": len(lines),
                    },
                }
            )
        return chunks

    def index_directory(self, root_dir: str | Path, *, max_files: int = 10000) -> dict[str, Any]:
        root = Path(root_dir).resolve()
        documents: list[dict[str, Any]] = []
        files_indexed = 0

        for path in sorted(root.rglob("*")):
            if files_indexed >= max_files:
                break
            if not path.is_file() or path.suffix not in SUPPORTED_CODE_EXTENSIONS:
                continue
            rel_parts = path.relative_to(root).parts
            if any(
                part in IGNORED_DIRS or part.startswith(".") or part.startswith("results-")
                for part in rel_parts[:-1]
            ):
                continue
            rel_path = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not source.strip():
                continue
            files_indexed += 1
            if path.suffix == ".py":
                documents.extend(self._extract_python_chunks(rel_path, source))
            else:
                lines = source.splitlines()
                lang = EXTENSION_LANGUAGE_MAP.get(path.suffix, path.suffix.lstrip("."))
                documents.append(
                    {
                        "id": f"code::{rel_path}::module",
                        "text": f"// File: {rel_path}\n{source[:4000]}",
                        "user_id": self.user_id,
                        "metadata": {
                            "modality": "code",
                            "language": lang,
                            "file_path": rel_path,
                            "symbol_name": path.stem,
                            "symbol_kind": "module",
                            "start_line": 1,
                            "end_line": len(lines),
                        },
                    }
                )

        batch_size = 200
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            self.client.ingest(
                documents=batch,
                user_id=self.user_id,
                namespace=self.namespace,
            )
        return {
            "root": str(root),
            "files_indexed": files_indexed,
            "symbols_indexed": len(documents),
        }


def search_code_by_behavior(
    client: MemoryClient,
    query: str,
    *,
    top_k: int = 5,
    user_id: str = "repo",
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Search indexed code chunks by computational behavior via `/ ml` Cloud."""
    metadata_filter: dict[str, Any] = {"modality": "code"}
    if language:
        metadata_filter["language"] = language
    res = client.query(
        query,
        top_k=top_k,
        user_id=user_id,
        metadata_filter=metadata_filter,
    )
    return list(res.get("results") or [])


def find_bug_candidates(
    client: MemoryClient,
    bug_description: str,
    *,
    stack_trace: str = "",
    top_k: int = 5,
    user_id: str = "repo",
) -> list[dict[str, Any]]:
    """Rank candidate functions or modules likely responsible for a reported bug."""
    combined = f"{bug_description.strip()}\n{stack_trace.strip()}".strip()
    res = client.query(
        combined,
        top_k=top_k,
        user_id=user_id,
        metadata_filter={"modality": "code"},
    )
    return list(res.get("results") or [])


def remap_memory_file_references(
    client: MemoryClient,
    old_path: str,
    new_path: str,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Update stored memories referencing `old_path` so they point to `new_path`."""
    all_records = client.get_all(user_id=user_id).get("results", [])
    updated = 0
    for rec in all_records:
        mid = str(rec.get("id", ""))
        text = str(rec.get("memory") or rec.get("text") or "")
        meta = dict(rec.get("metadata") or {})
        if old_path in text or meta.get("file_path") == old_path:
            new_text = text.replace(old_path, new_path)
            if meta.get("file_path") == old_path:
                meta["file_path"] = new_path
            client.update(mid, text=new_text, metadata=meta)
            updated += 1
    return {"old_path": old_path, "new_path": new_path, "records_updated": updated}
