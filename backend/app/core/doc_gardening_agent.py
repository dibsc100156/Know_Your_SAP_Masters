from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


CODE_REF_RE = re.compile(r"`([^`]+\.(?:py|md|json|yml|yaml|txt))`")


@dataclass
class DocIssue:
    severity: str  # info | warning | error
    issue_type: str
    file_path: str
    message: str
    confidence: float
    risk: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "severity": self.severity,
            "issue_type": self.issue_type,
            "file_path": self.file_path,
            "message": self.message,
            "confidence": self.confidence,
            "risk": self.risk,
        }


class DocGardeningAgent:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.docs_root = self.repo_root / "docs"

    def scan(self) -> Dict[str, object]:
        docs = sorted(self.docs_root.glob("*.md"))
        issues: List[DocIssue] = []
        referenced = set()

        for doc in docs:
            text = doc.read_text(encoding="utf-8", errors="ignore")
            refs = CODE_REF_RE.findall(text)
            for ref in refs:
                normalized = ref.replace("\\", "/")
                referenced.add(normalized)
                if not (self.repo_root / normalized).exists():
                    issues.append(DocIssue(
                        severity="error",
                        issue_type="broken_reference",
                        file_path=str(doc.relative_to(self.repo_root)).replace("\\", "/"),
                        message=f"Referenced file does not exist: {normalized}",
                        confidence=0.97,
                        risk="low",
                    ))
            if "TODO" in text or "TBD" in text:
                issues.append(DocIssue(
                    severity="warning",
                    issue_type="stale_placeholder",
                    file_path=str(doc.relative_to(self.repo_root)).replace("\\", "/"),
                    message="Document still contains TODO/TBD placeholders.",
                    confidence=0.72,
                    risk="low",
                ))

        for doc in docs:
            rel = str(doc.relative_to(self.repo_root)).replace("\\", "/")
            if rel not in referenced and doc.name not in {"LEVEL5_ROADMAP.md", "LEVEL5_PUNCHLIST.md"}:
                issues.append(DocIssue(
                    severity="info",
                    issue_type="orphan_doc",
                    file_path=rel,
                    message="Doc appears unreferenced by other markdown/code refs in docs scan.",
                    confidence=0.55,
                    risk="low",
                ))

        issues.sort(key=lambda i: {"error": 0, "warning": 1, "info": 2}[i.severity])
        return {
            "status": "ok" if not any(i.severity == "error" for i in issues) else "needs_attention",
            "doc_count": len(docs),
            "issue_count": len(issues),
            "issues": [i.to_dict() for i in issues],
        }
