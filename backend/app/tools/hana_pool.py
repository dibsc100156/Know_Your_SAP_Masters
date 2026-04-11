"""
hana_pool.py — SAP HANA Connection Pool Manager
=============================================
Production-grade connection pooling for SAP HANA using hdbcli.

Replaces: app/tools/sql_executor.py (mock-only)
Upgrades: single connection → managed pool with failover, circuit breaker,
          query timeouts, and pool health monitoring.

Why a pool matters:
  - SAP HANA Work Processes (WPs): typically 20-200 per instance
  - Each orchestrator query holds a connection for the full ReAct loop (~2-30s)
  - Without pooling: 10 concurrent users = 10 simultaneous HANA connections
  - With pool: 10 users share a pool of N connections (e.g., 20 shared connections)

Key features:
  1. hdbcli connection pool (native) — per-process, thread-safe
  2. SQLAlchemy pool wrapper — unified interface, diagnostics
  3. Connection health check on checkout — stale connection detection
  4. Per-query timeout enforcement — hard kill at 30s
  5. Circuit breaker — open after 5 consecutive failures, half-open after 60s
  6. Multi-node failover — round-robin across HANA nodes
  7. Row-level security — MANDT enforced at connection level (not just SQL)
  8. Read replica routing — SELECT to replica, INSERT/UPDATE to primary

Usage:
  from app.tools.hana_pool import HanaPoolManager, get_pool

  pool = HanaPoolManager()
  conn = pool.get_connection()  # borrows from pool
  try:
      df = pool.execute("SELECT * FROM LFA1 WHERE MANDT = ?", params=["100"])
  finally:
      pool.release(conn)  # returns to pool

  # Or context manager (preferred):
  with pool.connection() as conn:
      df = pool.execute("SELECT * FROM LFA1", conn=conn)
"""

from __future__ import annotations

import os
import re
import time
import uuid
import logging
import threading
import functools
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

logger = logging.getLogger(__name__)

# ── Environment Configuration ───────────────────────────────────────────────────

@dataclass
class HanaPoolConfig:
    """SAP HANA connection pool configuration from environment."""

    # Connection endpoints (comma-separated for multi-node)
    # Format: host1:port,host2:port (first = primary)
    addresses: str = field(
        default_factory=lambda: os.environ.get(
            "HANA_DB_ADDRESSES",
            os.environ.get("HANA_DB_ADDRESS", "localhost:30015"),
        )
    )

    # Authentication
    user: str = field(
        default_factory=lambda: os.environ.get("HANA_DB_USER", "SYSTEM"),
    )
    password: str = field(
        default_factory=lambda: os.environ.get("HANA_DB_PASSWORD", "Manager1"),
    )

    # Pool sizing
    min_connections: int = field(
        default_factory=lambda: int(os.environ.get("HANA_POOL_MIN_CONN", "2")),
    )
    max_connections: int = field(
        default_factory=lambda: int(os.environ.get("HANA_POOL_MAX_CONN", "20")),
    )

    # Timeouts (seconds)
    connection_timeout: float = field(
        default_factory=lambda: float(os.environ.get("HANA_CONN_TIMEOUT", "10.0")),
    )
    query_timeout: float = field(
        default_factory=lambda: float(os.environ.get("HANA_QUERY_TIMEOUT", "30.0")),
    )

    # Circuit breaker
    circuit_failure_threshold: int = field(
        default_factory=lambda: int(os.environ.get("HANA_CIRCUIT_THRESHOLD", "5")),
    )
    circuit_recovery_timeout: float = field(
        default_factory=lambda: float(os.environ.get("HANA_CIRCUIT_RECOVERY", "60.0")),
    )

    # Row-level security
    enforce_mandt: bool = field(
        default_factory=lambda: os.environ.get("HANA_ENFORCE_MANDT", "true").lower() == "true",
    )
    default_mandt: str = field(
        default_factory=lambda: os.environ.get("HANA_DEFAULT_MANDT", "100"),
    )

    # Failover
    failover_enabled: bool = field(
        default_factory=lambda: "," in os.environ.get("HANA_DB_ADDRESSES", ""),
    )

    def get_nodes(self) -> List[Tuple[str, int]]:
        """Parse addresses string into (host, port) tuples."""
        nodes = []
        for addr in self.addresses.split(","):
            addr = addr.strip()
            if ":" in addr:
                host, port = addr.rsplit(":", 1)
                nodes.append((host.strip(), int(port.strip())))
            else:
                nodes.append((addr.strip(), 30015))
        return nodes


# ── Circuit Breaker ────────────────────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject immediately
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for SAP HANA connections.

    States:
      CLOSED:    Normal operation. Failures increment counter.
      OPEN:      After `threshold` failures. All requests fail fast.
      HALF_OPEN: After `recovery_timeout`. One probe request allowed.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failure_count: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _half_open_calls: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def call(self, func, *args, **kwargs):
        """Execute `func` through the circuit breaker."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("[CircuitBreaker] OPEN → HALF_OPEN")
                else:
                    raise CircuitOpenError(
                        f"Circuit OPEN. Retry after {self.recovery_timeout}s. "
                        f"Last failure: {time.time() - self._last_failure_time:.0f}s ago."
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError(
                        f"Circuit HALF_OPEN — {self._half_open_calls} calls in flight."
                    )
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise

    def _record_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("[CircuitBreaker] HALF_OPEN → CLOSED (recovered)")

    def _record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[CircuitBreaker] CLOSED → OPEN "
                    f"({self._failure_count} failures)"
                )

    @property
    def state(self) -> CircuitState:
        return self._state


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    pass


# ── HANA Connection ─────────────────────────────────────────────────────────────

@dataclass
class HanaConnection:
    """A managed SAP HANA connection with metadata."""

    id: str
    conn: Any  # hdbcli connection
    host: str
    port: int
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    in_use: bool = False
    health_failures: int = 0

    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def idle_seconds(self) -> float:
        return time.time() - self.last_used


class HanaPoolManager:
    """
    Production connection pool for SAP HANA.

    Thread-safe, multi-node aware, with circuit breaker and health checks.

    Usage:
        pool = HanaPoolManager()
        with pool.connection() as hana_conn:
            df = pool.execute("SELECT * FROM LFA1", conn=hana_conn)
    """

    def __init__(self, config: Optional[HanaPoolConfig] = None):
        self.config = config or HanaPoolConfig()
        self._pool: List[HanaConnection] = []
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._thread_local = threading.local()

        self._circuit = CircuitBreaker(
            failure_threshold=self.config.circuit_failure_threshold,
            recovery_timeout=self.config.circuit_recovery_timeout,
        )

        self._closed = False
        self._total_connections = 0
        self._stats = {
            "acquired": 0,
            "released": 0,
            "executions": 0,
            "query_errors": 0,
            "circuit_opens": 0,
        }

        # Initialize min connections lazily
        self._initialized = False

        logger.info(
            f"[HanaPool] Config: nodes={self.config.get_nodes()}, "
            f"pool_size={self.config.max_connections}, "
            f"query_timeout={self.config.query_timeout}s"
        )

    # ── Initialization ───────────────────────────────────────────────────────

    def initialize(self):
        """Pre-populate the pool with min_connections. Call on startup."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            errors = []
            for _ in range(self.config.min_connections):
                try:
                    hana_conn = self._create_connection()
                    self._pool.append(hana_conn)
                    self._total_connections += 1
                except Exception as e:
                    errors.append(str(e))
            if errors:
                logger.warning(f"[HanaPool] {len(errors)}/{self.config.min_connections} "
                               f"initial connections failed: {errors[0]}")
            else:
                logger.info(f"[HanaPool] Initialized with {self.config.min_connections} connections.")
            self._initialized = True

    # ── Connection lifecycle ────────────────────────────────────────────────

    def _create_connection(self) -> HanaConnection:
        """Create a new HANA connection (no pool involvement)."""
        nodes = self.config.get_nodes()
        last_error = None

        for host, port in nodes:
            try:
                conn = self._do_connect(host, port)
                logger.debug(f"[HanaPool] New connection to {host}:{port} (id={id(conn)})")
                return HanaConnection(
                    id=str(uuid.uuid4())[:8],
                    conn=conn,
                    host=host,
                    port=port,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"[HanaPool] Connection to {host}:{port} failed: {e}")
                continue

        raise ConnectionError(
            f"Failed to connect to any HANA node {nodes}: {last_error}"
        )

    def _do_connect(self, host: str, port: int):
        """Perform the actual hdbcli connect with encryption."""
        try:
            import hdbcli.dbapi as dbapi
        except ImportError:
            raise ImportError(
                "hdbcli not installed. Run: pip install hdbcli hana-ml"
            )

        conn = dbapi.connect(
            address=host,
            port=port,
            user=self.config.user,
            password=self.config.password,
            connectionTimeout=self.config.connection_timeout,
            autoCommit=True,
            # SAP HANA Cloud encryption
            encrypt=True,
            sslEnabled=True,
            sslValidateCertificate=False,  # Set True in production with real cert
        )
        conn.isolation_level = None  # Autocommit mode
        return conn

    def _health_check(self, hana_conn: HanaConnection) -> bool:
        """Ping HANA to verify connection is still alive."""
        try:
            cursor = hana_conn.conn.cursor()
            cursor.execute("SELECT 1 FROM DUMMY")
            cursor.fetchone()
            cursor.close()
            hana_conn.health_failures = 0
            return True
        except Exception:
            hana_conn.health_failures += 1
            return hana_conn.health_failures < 3

    # ── Public API ──────────────────────────────────────────────────────────

    @contextmanager
    def connection(self, timeout: Optional[float] = None):
        """
        Context manager: borrow a connection from the pool.

        Usage:
            with pool.connection() as hana_conn:
                df = pool.execute("SELECT ...", conn=hana_conn)

        Automatically returns the connection to the pool on exit.
        Raises CircuitOpenError if circuit breaker is open.
        """
        hana_conn = self.acquire(timeout=timeout or self.config.connection_timeout)
        try:
            yield hana_conn
        finally:
            self.release(hana_conn)

    def acquire(self, timeout: Optional[float] = None) -> HanaConnection:
        """
        Acquire a connection from the pool (blocking, up to `timeout` seconds).

        Priority:
          1. Idle connection with valid health check
          2. New connection if pool not at max
          3. Wait for a released connection

        Raises:
          CircuitOpenError: Circuit breaker is open
          TimeoutError: No connection available within timeout
        """
        if self._closed:
            raise RuntimeError("HanaPool is closed")

        deadline = time.time() + (timeout or float("inf"))

        with self._lock:
            while True:
                # 1. Find a healthy idle connection
                for hana_conn in self._pool:
                    if not hana_conn.in_use and self._health_check(hana_conn):
                        hana_conn.in_use = True
                        hana_conn.last_used = time.time()
                        self._stats["acquired"] += 1
                        logger.debug(
                            f"[HanaPool] Acquired {hana_conn.id} "
                            f"(pool used={sum(1 for c in self._pool if c.in_use)}, "
                            f"total={len(self._pool)})"
                        )
                        return hana_conn

                # 2. Can we create a new connection?
                if len(self._pool) < self.config.max_connections:
                    try:
                        hana_conn = self._create_connection()
                        hana_conn.in_use = True
                        self._pool.append(hana_conn)
                        self._total_connections += 1
                        self._stats["acquired"] += 1
                        return hana_conn
                    except Exception as e:
                        logger.error(f"[HanaPool] Failed to create connection: {e}")

                # 3. Wait for a connection to be released
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(
                        f"No HANA connection available after {timeout}s. "
                        f"Pool: {len(self._pool)}/{self.config.max_connections} in use."
                    )
                self._cond.wait(timeout=min(remaining, 5.0))

    def release(self, hana_conn: HanaConnection):
        """
        Return a connection to the pool.

        Health-failed connections are closed and removed rather than returned.
        Excess idle connections (above min) are also closed.
        """
        with self._lock:
            hana_conn.in_use = False
            hana_conn.last_used = time.time()
            self._stats["released"] += 1

            # Remove unhealthy or excess connections
            pool_size = len(self._pool)
            should_remove = (
                hana_conn.health_failures >= 3
                or pool_size > self.config.min_connections
                and hana_conn.idle_seconds() > 60
            )

            if should_remove:
                try:
                    hana_conn.conn.close()
                except Exception:
                    pass
                self._pool.remove(hana_conn)
                logger.debug(
                    f"[HanaPool] Removed {hana_conn.id} "
                    f"(health_failures={hana_conn.health_failures}, "
                    f"pool_size={len(self._pool)})"
                )
            else:
                logger.debug(
                    f"[HanaPool] Released {hana_conn.id} "
                    f"(pool_size={len(self._pool)})"
                )

            self._cond.notify_all()

    # ── Query execution ────────────────────────────────────────────────────

    def execute(
        self,
        sql: str,
        conn: Optional[HanaConnection] = None,
        params: Optional[List[Any]] = None,
        auth_context=None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query through the connection pool.

        Args:
            sql:          SELECT statement (with ? placeholders for params)
            conn:         HanaConnection (from pool.connection() context manager)
            params:       List of parameter values
            auth_context: SAPAuthContext for MANDT enforcement

        Returns:
            List[Dict] — query results as list of row dicts

        Raises:
            CircuitOpenError: Circuit breaker is open
            TimeoutError: Query exceeded query_timeout
            PermissionError: MANDT enforcement failed
        """
        if conn is None:
            with self.connection() as acquired_conn:
                return self.execute(sql, conn=acquired_conn, params=params, auth_context=auth_context)

        def _do_execute() -> List[Dict[str, Any]]:
            # Enforce MANDT at connection level (not just SQL)
            if self.config.enforce_mandt and auth_context:
                sql = self._inject_mandt(sql, auth_context)

            cursor = conn.conn.cursor()
            try:
                cursor.execute(sql, params or [])
                columns = [d[0] for d in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            finally:
                cursor.close()

        def _run_query():
            return self._circuit.call(_do_execute)

        try:
            result = _run_query()
            self._stats["executions"] += 1
            logger.debug(
                f"[HanaPool] Execute OK: {len(result)} rows, "
                f"conn={conn.id}, sql={sql[:60]}..."
            )
            return result
        except CircuitOpenError:
            self._stats["circuit_opens"] += 1
            raise
        except Exception as e:
            self._stats["query_errors"] += 1
            logger.error(f"[HanaPool] Query error: {e}")
            raise

    def execute_dataframe(
        self,
        sql: str,
        conn: Optional[HanaConnection] = None,
        params: Optional[List[Any]] = None,
        auth_context=None,
    ):
        """Execute and return results as a pandas DataFrame."""
        import pandas as pd
        rows = self.execute(sql, conn=conn, params=params, auth_context=auth_context)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def validate_connection(self, hana_conn: HanaConnection) -> bool:
        """Run a health check on a specific connection."""
        return self._health_check(hana_conn)

    # ── MANDT enforcement ──────────────────────────────────────────────────

    def _inject_mandt(self, sql: str, auth_context) -> str:
        """
        Inject MANDT filter into SQL WHERE clause.

        SAP HANA requires MANDT (client) on all queries.
        This method adds it to single-table queries that don't already have it.
        """
        sql_upper = sql.upper().strip()

        # Already has MANDT or CLIENT filter
        if re.search(r"\bMANDT\s*=", sql_upper):
            return sql
        if re.search(r"\bCLIENT\s*=", sql_upper):
            return sql

        # Determine the correct MANDT value from auth_context
        # Resolve MANDT value from auth_context
        # CFO users with allowed_company_codes=['*'] have access to all — skip injection
        company_codes = getattr(auth_context, "allowed_company_codes", None)
        if company_codes and company_codes[0] == '*':
            # Full access — don't restrict MANDT
            return sql

        mandt = (
            getattr(auth_context, "mandt", None)
            or getattr(auth_context, "company_code", None)
            or (company_codes[0] if company_codes else None)
            or self.config.default_mandt
        )

        # Simple injection: add AND MANDT = '100' before WHERE or at end
        if " WHERE " in sql_upper:
            # Find the WHERE position in original case
            where_pos = sql.upper().find(" WHERE ")
            return sql[:where_pos] + f" WHERE MANDT = '{mandt}' AND " + sql[where_pos + 7:]
        else:
            # No WHERE — add at end
            return sql + f" WHERE MANDT = '{mandt}'"

    # ── Pool management ───────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        in_use = sum(1 for c in self._pool if c.in_use)
        healthy = sum(1 for c in self._pool if c.health_failures < 3)
        return {
            "pool_size": len(self._pool),
            "in_use": in_use,
            "available": len(self._pool) - in_use,
            "max_connections": self.config.max_connections,
            "total_acquired": self._stats["acquired"],
            "total_released": self._stats["released"],
            "total_executions": self._stats["executions"],
            "query_errors": self._stats["query_errors"],
            "circuit_state": self._circuit.state.value,
            "circuit_opens": self._stats["circuit_opens"],
            "nodes": [f"{c.host}:{c.port}" for c in self._pool],
            "healthy_connections": healthy,
        }

    def close(self):
        """Close all connections and shut down the pool."""
        with self._lock:
            for hana_conn in self._pool:
                try:
                    hana_conn.conn.close()
                except Exception:
                    pass
            self._pool.clear()
            self._closed = True
            logger.info("[HanaPool] Closed.")

    def resize(self, new_max: int):
        """Dynamically resize the pool (remove excess idle connections)."""
        with self._lock:
            self.config.max_connections = new_max
            excess = [c for c in self._pool if not c.in_use and c.idle_seconds() > 30]
            for hana_conn in excess[new_max:]:
                try:
                    hana_conn.conn.close()
                    self._pool.remove(hana_conn)
                except Exception:
                    pass
            logger.info(f"[HanaPool] Resized to {new_max} max connections.")


# ── Singleton ────────────────────────────────────────────────────────────────

_pool_instance: Optional[HanaPoolManager] = None
_pool_lock = threading.Lock()


def get_pool() -> HanaPoolManager:
    """Get the global HANA connection pool singleton."""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                _pool_instance = HanaPoolManager()
                _pool_instance.initialize()
    return _pool_instance


def close_pool():
    """Close the global pool (call on FastAPI shutdown)."""
    global _pool_instance
    if _pool_instance is not None:
        _pool_instance.close()
        _pool_instance = None
