"""
sql_patterns — SAP Master Data SQL Pattern Library

Comprehensive proven SQL patterns for all 18 SAP Master Data domains.
Each pattern includes: intent description, business use case, and ready-to-use SQL.

Usage:
    from app.core.sql_patterns.library import get_all_patterns, PATTERNS_BY_DOMAIN, get_patterns_for_domain
"""

from app.core.sql_patterns.library import (
    PATTERNS_BY_DOMAIN,
    get_all_patterns,
    get_patterns_for_domain,
    get_pattern_count,
)

__all__ = [
    "PATTERNS_BY_DOMAIN",
    "get_all_patterns",
    "get_patterns_for_domain",
    "get_pattern_count",
]
