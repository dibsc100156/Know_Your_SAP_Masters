from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ReviewFinding:
    reviewer: str
    severity: str  # info | warning | blocking
    category: str
    message: str
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        return {
            "reviewer": self.reviewer,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "file_path": self.file_path,
        }


@dataclass
class ReviewPass:
    reviewer: str
    findings: List[ReviewFinding] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "reviewer": self.reviewer,
            "findings": [f.to_dict() for f in self.findings],
            "blocking_count": sum(1 for f in self.findings if f.severity == "blocking"),
        }


class RalphWiggumPRReviewLoop:
    """
    Lightweight PR review harness:
      self-review -> specialist reviews -> iterate until stable -> merge recommendation.

    This is intentionally deterministic and local-first so it can run without GitHub API access.
    """

    DEFAULT_REVIEWERS = ("quality", "security", "docs")

    def submit_self_review(
        self,
        *,
        pr_title: str,
        changed_files: List[str],
        diff_summary: str,
        tests_added: bool,
        docs_updated: bool,
    ) -> Dict[str, object]:
        findings: List[ReviewFinding] = []
        if not tests_added:
            findings.append(ReviewFinding("self", "blocking", "tests", "PR is missing targeted tests."))
        if any(path.endswith(".md") for path in changed_files) and not docs_updated:
            findings.append(ReviewFinding("self", "warning", "docs", "Markdown changes detected without explicit doc refresh acknowledgement."))
        if len(changed_files) > 20:
            findings.append(ReviewFinding("self", "warning", "scope", "PR is broad; consider splitting for easier review."))
        if "WIP" in pr_title.upper():
            findings.append(ReviewFinding("self", "blocking", "title", "PR title still marked WIP."))
        return {
            "reviewer": "self",
            "summary": "Self-review completed",
            "findings": [f.to_dict() for f in findings],
        }

    def request_agent_reviews(
        self,
        *,
        changed_files: List[str],
        diff_summary: str,
        reviewers: Optional[List[str]] = None,
        docs_updated: bool = False,
        tests_added: bool = False,
    ) -> List[Dict[str, object]]:
        reviewers = reviewers or list(self.DEFAULT_REVIEWERS)
        passes: List[ReviewPass] = []
        for reviewer in reviewers:
            findings: List[ReviewFinding] = []
            if reviewer == "quality":
                if not tests_added:
                    findings.append(ReviewFinding(reviewer, "blocking", "tests", "Quality review requires targeted tests for changed behavior."))
                if any("orchestrator.py" in p for p in changed_files) and "benchmark" not in diff_summary.lower():
                    findings.append(ReviewFinding(reviewer, "warning", "benchmark", "Core orchestration changed without benchmark mention."))
            elif reviewer == "security":
                if any("api" in p.lower() for p in changed_files) and "auth" not in diff_summary.lower() and "security" not in diff_summary.lower():
                    findings.append(ReviewFinding(reviewer, "warning", "security", "API changes should mention auth/safety impact."))
            elif reviewer == "docs":
                if any(p.endswith(".py") for p in changed_files) and not docs_updated:
                    findings.append(ReviewFinding(reviewer, "warning", "docs", "Code changed without corresponding docs update."))
            passes.append(ReviewPass(reviewer=reviewer, findings=findings))
        return [p.to_dict() for p in passes]

    def iterate_until_stable(
        self,
        *,
        pr_title: str,
        changed_files: List[str],
        diff_summary: str,
        tests_added: bool,
        docs_updated: bool,
        max_rounds: int = 2,
    ) -> Dict[str, object]:
        history = []
        current_tests = tests_added
        current_docs = docs_updated
        stable = False

        for round_idx in range(1, max_rounds + 1):
            self_review = self.submit_self_review(
                pr_title=pr_title,
                changed_files=changed_files,
                diff_summary=diff_summary,
                tests_added=current_tests,
                docs_updated=current_docs,
            )
            specialist = self.request_agent_reviews(
                changed_files=changed_files,
                diff_summary=diff_summary,
                tests_added=current_tests,
                docs_updated=current_docs,
            )
            all_findings = list(self_review["findings"])
            for review_pass in specialist:
                all_findings.extend(review_pass["findings"])

            blocking = [f for f in all_findings if f["severity"] == "blocking"]
            warnings = [f for f in all_findings if f["severity"] == "warning"]
            history.append({
                "round": round_idx,
                "self_review": self_review,
                "specialist_reviews": specialist,
                "blocking_count": len(blocking),
                "warning_count": len(warnings),
            })

            if not blocking:
                stable = True
                break

            # Simulated remediation hooks for deterministic iteration.
            current_tests = current_tests or any(f["category"] == "tests" for f in blocking)
            current_docs = current_docs or any(f["category"] == "docs" for f in warnings)

        final_findings = history[-1]["self_review"]["findings"][:]
        for review_pass in history[-1]["specialist_reviews"]:
            final_findings.extend(review_pass["findings"])
        blocking_count = sum(1 for f in final_findings if f["severity"] == "blocking")
        warning_count = sum(1 for f in final_findings if f["severity"] == "warning")
        return {
            "status": "approved" if blocking_count == 0 else "changes_requested",
            "stable": stable,
            "rounds": len(history),
            "blocking_count": blocking_count,
            "warning_count": warning_count,
            "auto_merge_eligible": blocking_count == 0,
            "history": history,
        }
