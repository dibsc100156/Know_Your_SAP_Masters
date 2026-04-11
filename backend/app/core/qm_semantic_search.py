"""
qm_semantic_search.py — Phase 8: QM Long-Text Semantic Search
=========================================================
Embeds 20 years of SAP QM free-text maintenance notifications into
ChromaDB so that mechanic notes, defect descriptions, and failure
reports become semantically searchable.

Why this matters:
  A mechanic in 2009 wrote: "Bearing B-2047 showing fatigue signs —
  recommend replacement at next planned shutdown." This text contains
  the REASON why a maintenance decision was made. This reason is not
  in any structured field. It lives only in QMEL-QMTXT (long text).

  Without semantic search, this text is locked in a database blob.
  With it, a planner in 2026 can query: "bearing vibration fatigue"
  and find this exact historical note, connecting a present-day
  vibration reading to a 17-year-old warning.

What gets embedded:
  QMEL-QMTXT     — Quality notification long text (mechanic's own words)
  QMEL-QMTXTV    — Long text versions (alternate language if available)
  VIQMEL-LONGTEXT — QM notification long text (more detailed)
  AFIH-IMSTG     — Maintenance order: long text description
  IHPA-TXLBZ     — Partner notes (who reported what, in their own words)
  QALS-TXTCR     — Inspection lot characteristic results text

Embedding pipeline:
  1. Extract raw QM notification texts from SAP (or mock data)
  2. Chunk long texts by sentence or paragraph (max 512 tokens)
  3. Generate metadata: year, plant, equipment, notification type, priority
  4. Embed via sentence-transformers (all-MiniLM-L6-v2)
  5. Store in ChromaDB collection: qm_semantic_notifications
  6. Query: semantic search → returns relevant historical notes

Usage:
  from app.core.qm_semantic_search import QMSemanticSearch
  qm = QMSemanticSearch()

  # Index QM notifications (run once on setup or periodically)
  qm.index_notifications(query="extract all QM notification texts")

  # Search historical notes
  results = qm.search(
      query="bearing vibration fatigue",
      plant="PLANT-100",
      year_range=(2010, 2025),
      top_k=10,
  )
  for r in results:
      print(f"[{r['year']}] {r['equipment']}: {r['text'][:100]}...")

  # Contextual search: what did we see before this failure?
  context = qm.get_failure_context(
      equipment="EQUIP-B2047",
      before_year=2026,
      years_back=5,
  )
"""

import re
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass
from pathlib import Path

from app.core.memory_layer import sap_memory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QM_CHROMA_DIR = Path.home() / ".openclaw" / "workspace" / "chroma_qm_db"
COLLECTION_NAME = "qm_semantic_notifications"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 300        # max characters per chunk
CHUNK_OVERLAP = 50      # overlap between chunks
TOP_K_DEFAULT = 10


# ---------------------------------------------------------------------------
# QM Notification Text Extractor
# ---------------------------------------------------------------------------

@dataclass
class QMNotificationText:
    """A single QM notification text with metadata."""
    notification_no: str      # QMEL-QMNUM
    notification_type: str     # QMEL-QMART (M1=Complaint, Q2=Nonconformance, etc.)
    priority: str              # QMEL-QPRIOR (1=Critical, 2=High, 3=Medium, 4=Low)
    plant: str                # QMEL-IWERK
    equipment: str            # QMEL-ILOAN (equipment list)
    functional_loc: str        # QMEL-TPLNR (functional location)
    material: str             # QMEL-MATNR
    description: str          # QMEL-QMTXT (short text)
    long_text: str            # QMEL-QMTXTV / VIQMEL-LONGTEXT
    created_by: str           # QMEL-ERNAM
    created_date: str         # QMEL-QMDAT (YYYYMMDD)
    year: int
    task_list_type: str       # AFIH-TASK_TXT or MAPL description
    task_text: str           # AFIH-IMSTG (maintenance order long text)
    part_cause: str          # IHPA-TXLBZ (partner notes — cause description)
    search_chunk_id: str


class QMTextExtractor:
    """
    Extracts and chunks QM notification texts from SAP.
    In production, this queries QMEL, VIQMEL, AFIH, IHPA tables.
    For demo, it generates realistic mock texts based on QM patterns.
    """

    # Template patterns for realistic mock QM texts
    DEFECT_TEMPLATES = [
        "Machine {equipment} at {location}: {symptom}. "
        "Technician notes: {detail}. "
        "Previous occurrence: {prior}. "
        "Recommended action: {action}.",
        "Equipment {equipment} ({func_loc}) showing {symptom}. "
        "Root cause identified as {root_cause}. "
        "Countermeasure: {countermeasure}. "
        "Status: {status}.",
        "{symptom} reported on {equipment} line {line}. "
        "Frequency: {frequency}. "
        "Impact: {impact}. "
        "Action taken: {action_taken}. "
        "Follow-up required: {followup}.",
    ]

    SYMPTOMS = [
        "abnormal vibration", "elevated temperature", "unusual noise",
        "material defect", "dimensional variance", "surface finish issue",
        "misalignment detected", "worn bearing", "lubrication contamination",
        "corrosion observed", "crack propagation", "electrical fault",
        "calibration drift", "material hardness below spec",
        "batch rejection for {reason}", "seal leakage", "bolt fatigue",
    ]

    ROOT_CAUSES = [
        "insufficient lubrication interval", "over-speed operation",
        "thermal expansion beyond design tolerance", "material batch variation",
        "operator handling error", "supplier quality deviation",
        "maintenance deferral — previously flagged in {year}",
        "installation error", "design margin exceeded",
        "contamination during assembly", "storage conditions non-compliant",
    ]

    ACTIONS = [
        "replaced component", "adjusted parameters", "tightened schedule",
        "escalated to engineering review", "created maintenance order",
        "ordered spare parts", "scheduled next inspection",
        "issued NCR (Non-Conformance Report)", "placed on hold",
        "root cause analysis initiated", "countermeasure documented in work order",
    ]

    EQUIPMENT_IDS = [
        "B-2047", "MTR-033", "PMP-101", "CONV-220", "CHP-07",
        "TURB-L3", "HEX-45", "COMP-A1", "MILL-12", "CNC-05",
        "ROBOT-3", "SPR-PLT", "PUMP-A7", "VLV-220", "FLT-10",
    ]

    FUNCTIONAL_LOCS = [
        "PLANT-100-AREA-A", "PLANT-100-AREA-B", "PLANT-100-UTILITY",
        "PLANT-200-PROD", "PLANT-200-PACK", "WAREHOUSE-01",
        "UTILITY-STEAM", "UTILITY-AIR", "UTILITY-WATER",
    ]

    def __init__(self):
        self._rng_seed = 42  # reproducible for demo

    def generate_mock_notifications(
        self,
        count: int = 500,
        year_start: int = 2005,
        year_end: int = 2025,
        plant_filter: Optional[str] = None,
    ) -> List[QMNotificationText]:
        """
        Generate realistic mock QM notifications for demo/testing.
        In production, replace with real SAP QMEL, VIQMEL, AFIH, IHPA queries.
        """
        import random
        random.seed(self._rng_seed)

        notifications = []
        years = list(range(year_start, year_end + 1))
        plants = ["PLANT-100", "PLANT-200", "WAREHOUSE-01"] if not plant_filter else [plant_filter]

        for i in range(count):
            year = random.choice(years)
            month = random.randint(1, 12)
            day = random.randint(1, 28)
            notification_no = f"QM-{year}-{i+1:05d}"

            plant = random.choice(plants)
            equipment = random.choice(self.EQUIPMENT_IDS)
            func_loc = random.choice(self.FUNCTIONAL_LOCS)
            priority = random.choice(["1", "2", "3", "4"])
            notif_type = random.choice(["M1", "M2", "Q2", "Q3"])

            symptom = random.choice(self.SYMPTOMS).format(reason=random.choice(["contamination", "tolerance", "hardness"]))
            root_cause = random.choice(self.ROOT_CAUSES).format(year=random.randint(2015, 2024))
            action = random.choice(self.ACTIONS)
            status = random.choice(["open", "in-work", "closed", "closed"])

            template = random.choice(self.DEFECT_TEMPLATES)
            long_text = template.format(
                equipment=equipment,
                location=func_loc,
                symptom=symptom,
                detail=f"Technician: {random.choice(['JSmith', 'RPatel', 'MChen', 'ALopez'])} — "
                       f"flagged during {random.choice(['PM round', 'shift handover', 'breakdown', 'quality inspection'])}",
                prior=f"First occurrence: {year - random.randint(1, 5)}" if random.random() > 0.3 else "No prior occurrence",
                action=action,
                func_loc=func_loc,
                root_cause=root_cause,
                countermeasure=random.choice(["lubrication schedule increased", "alignment check added",
                                            "supplier audit initiated", "PM frequency doubled"]),
                status=status,
                line=random.randint(1, 8),
                frequency=random.choice(["intermittent", "constant", "increasing over 3 shifts", "seasonal"]),
                impact=random.choice(["line slowdown", "quality scrap", "safety concern", "delivery delay"]),
                action_taken=action,
                followup=f"Review by {random.choice(['maintenance manager', 'quality engineer', 'plant manager'])}",
            )

            chunk_id = hashlib.sha256(f"{notification_no}_{i}".encode()).hexdigest()[:16]

            notifications.append(QMNotificationText(
                notification_no=notification_no,
                notification_type=notif_type,
                priority=priority,
                plant=plant,
                equipment=equipment,
                functional_loc=func_loc,
                material=f"MAT-{random.randint(1000, 9999)}",
                description=symptom[:80],
                long_text=long_text,
                created_by=random.choice(["JSMITH", "RPATEL", "MCHEN", "ALOPEZ", "KDU"]),
                created_date=f"{year}{month:02d}{day:02d}",
                year=year,
                task_list_type=random.choice(["PM01", "QM01", "BREAKDOWN", "IM"]),
                task_text=long_text[:200],  # shortened for demo
                part_cause=f"Equipment {equipment} — {root_cause}"[:150],
                search_chunk_id=chunk_id,
            ))

        return notifications

    def chunk_text(
        self,
        text: str,
        chunk_size: int = CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
    ) -> List[str]:
        """
        Split long text into overlapping chunks.
        Chunks by sentence boundaries where possible.
        """
        # Split by sentence
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) <= chunk_size:
                current += " " + sentence
            else:
                if current.strip():
                    chunks.append(current.strip())
                # Overlap: keep last overlap chars of current for next chunk
                current = current[-overlap:] + " " + sentence if overlap > 0 else sentence

        if current.strip():
            chunks.append(current.strip())

        return chunks


# ---------------------------------------------------------------------------
# Semantic Search Engine
# ---------------------------------------------------------------------------

class QMSemanticSearch:
    """
    Semantic search over 20 years of QM notification texts.
    Builds a ChromaDB index of embedded notification chunks.
    Searches by semantic similarity + optional metadata filters.

    Uses sentence-transformers for embeddings (all-MiniLM-L6-v2).
    Falls back to keyword TF-IDF if transformer unavailable.
    """

    def __init__(self, chroma_dir: Optional[Path] = None):
        self.chroma_dir = Path(chroma_dir) if chroma_dir else QM_CHROMA_DIR
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = COLLECTION_NAME
        self._embedder = None
        self._client = None
        self._collection = None
        self._extractor = QMTextExtractor()
        self._use_transformers = False

        # Try to load sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(EMBEDDING_MODEL)
            self._use_transformers = True
        except ImportError:
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity
                self._tfidf = TfidfVectorizer(max_features=384, stop_words='english')
                self._tfidf_fitted = False
            except ImportError:
                self._tfidf = None

        # Try ChromaDB
        try:
            import chromadb
            self._client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
            )
            self._load_or_create_collection()
        except ImportError:
            self._client = None

    def _load_or_create_collection(self):
        if self._client is None:
            return
        try:
            self._collection = self._client.get_collection(name=self.collection_name)
        except Exception:
            self._collection = self._client.create_collection(
                name=self.collection_name,
                metadata={"description": "QM notification long-text semantic search"},
            )

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using sentence-transformers or TF-IDF fallback."""
        if self._use_transformers and self._embedder:
            embeddings = self._embedder.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()

        # TF-IDF fallback
        if self._tfidf:
            import numpy as np
            try:
                emb_matrix = self._tfidf.fit_transform(texts).toarray()
                self._tfidf_fitted = True
                return emb_matrix.tolist()
            except Exception:
                pass

        # Last resort: return zero vectors (search will use keyword only)
        return [[0.0] * 384 for _ in texts]

    def index_notifications(
        self,
        notifications: Optional[List[QMNotificationText]] = None,
        count: int = 500,
        year_start: int = 2005,
        year_end: int = 2025,
        plant: Optional[str] = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        Index QM notification texts into ChromaDB.
        If notifications is None, generates mock data.
        """
        if notifications is None:
            notifications = self._extractor.generate_mock_notifications(
                count=count,
                year_start=year_start,
                year_end=year_end,
                plant_filter=plant,
            )

        if self._collection is None:
            return {"indexed": 0, "status": "ChromaDB not available", "mode": "mock-only"}

        chunks = []
        metadatas = []
        ids = []

        chunk_count = 0
        for notif in notifications:
            text_chunks = self._extractor.chunk_text(notif.long_text)
            for chunk_idx, chunk in enumerate(text_chunks):
                chunk_id = f"{notif.search_chunk_id}_{chunk_idx}"
                chunks.append(chunk)
                metadatas.append({
                    "notification_no": notif.notification_no,
                    "notification_type": notif.notification_type,
                    "priority": notif.priority,
                    "plant": notif.plant,
                    "equipment": notif.equipment,
                    "functional_loc": notif.functional_loc,
                    "material": notif.material,
                    "year": notif.year,
                    "created_date": notif.created_date,
                    "created_by": notif.created_by,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(text_chunks),
                    "search_text": chunk[:500],  # store text for fallback keyword search
                })
                ids.append(chunk_id)
                chunk_count += 1

        # Embed
        if verbose:
            print(f"[QM-SEMANTIC] Embedding {len(chunks)} chunks with "
                  f"{'sentence-transformers' if self._use_transformers else 'TF-IDF'}...")

        embeddings = self._embed_texts(chunks)

        # Add to ChromaDB
        self._collection.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

        if verbose:
            print(f"[QM-SEMANTIC] Indexed {chunk_count} chunks from {len(notifications)} "
                  f"notifications into collection '{self.collection_name}'")

        # Log to memory
        sap_memory.log_schema_discovery(
            table="QMEL_notifications",
            domain="quality_management",
            discovered_via="qm_semantic_index",
            confidence=0.95,
            fields=["QMNUM", "QMTXT", "QMTXTV", "QMART", "QPRIOR", "IWERK"],
        )

        return {
            "indexed_notifications": len(notifications),
            "indexed_chunks": chunk_count,
            "collection": self.collection_name,
            "embedding_mode": "sentence-transformers" if self._use_transformers else "tfidf-fallback",
            "year_range": f"{year_start}-{year_end}",
        }

    def search(
        self,
        query: str,
        plant: Optional[str] = None,
        equipment: Optional[str] = None,
        year_range: Optional[tuple[int, int]] = None,
        priority_filter: Optional[List[str]] = None,
        top_k: int = TOP_K_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """
        Semantically search QM notification texts.

        Args:
            query: Natural language search query (e.g., "bearing vibration fatigue")
            plant: Filter by plant
            equipment: Filter by equipment ID
            year_range: (start_year, end_year) tuple
            priority_filter: List of priorities to include (["1","2"] = Critical + High)
            top_k: Number of results to return

        Returns:
            List of relevant historical QM notification chunks with metadata
        """
        if self._collection is None:
            return self._keyword_fallback_search(query, top_k)

        # Embed the query
        query_embedding = self._embed_texts([query])[0]

        # Build where filter
        where_filter: Dict[str, Any] = {}
        if plant:
            where_filter["plant"] = plant
        if equipment:
            where_filter["equipment"] = equipment
        if year_range:
            where_filter["year"] = {"$gte": year_range[0], "$lte": year_range[1]}
        if priority_filter:
            where_filter["priority"] = {"$in": priority_filter}

        # Query ChromaDB
        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter if where_filter else None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return self._keyword_fallback_search(query, top_k)

        # Format results
        formatted = []
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            formatted.append({
                "rank": i + 1,
                "notification_no": meta.get("notification_no", ""),
                "year": meta.get("year", 0),
                "equipment": meta.get("equipment", ""),
                "plant": meta.get("plant", ""),
                "priority": meta.get("priority", ""),
                "notification_type": meta.get("notification_type", ""),
                "text": doc,
                "similarity_score": round(1.0 - min(dist, 1.0), 4),  # convert distance to similarity
                "created_date": meta.get("created_date", ""),
                "created_by": meta.get("created_by", ""),
            })

        return formatted

    def get_failure_context(
        self,
        equipment: str,
        before_year: int,
        years_back: int = 5,
        query: str = "",
    ) -> Dict[str, Any]:
        """
        Find all QM notifications for an equipment in the years before
        a given year, plus an optional semantic search within those results.

        This answers: "What did we see about this equipment
        before the 2026 failure?"
        """
        start_year = before_year - years_back

        if query:
            # Semantic search within this equipment's history
            full_query = f"{equipment} {query}"
        else:
            full_query = equipment

        results = self.search(
            query=full_query,
            equipment=equipment,
            year_range=(start_year, before_year - 1),
            top_k=20,
        )

        if not results:
            return {
                "equipment": equipment,
                "period": f"{start_year}-{before_year - 1}",
                "total_notes": 0,
                "timeline": [],
                "summary": f"No QM notifications found for {equipment} in this period.",
            }

        # Build timeline
        timeline = sorted(results, key=lambda x: x["year"], reverse=True)
        critical = [r for r in timeline if r["priority"] == "1"]
        high = [r for r in timeline if r["priority"] == "2"]

        summary_parts = []
        if critical:
            summary_parts.append(f"{len(critical)} critical notification(s)")
        if high:
            summary_parts.append(f"{len(high)} high-priority notification(s)")
        if not summary_parts:
            summary_parts.append(f"{len(timeline)} notification(s)")

        return {
            "equipment": equipment,
            "period": f"{start_year}-{before_year - 1}",
            "total_notes": len(timeline),
            "critical_count": len(critical),
            "high_count": len(high),
            "timeline": timeline,
            "summary": f"Found {', '.join(summary_parts)} for {equipment}. "
                      f"Most recent: {timeline[0]['year']} "
                      f"(priority {timeline[0]['priority']}): "
                      f"{timeline[0]['text'][:100]}...",
            "top_texts": [r["text"][:200] for r in timeline[:5]],
        }

    def _keyword_fallback_search(
        self,
        query: str,
        top_k: int = TOP_K_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """
        Fallback keyword search when ChromaDB is not available.
        Uses stored metadata + text for simple filtering.
        """
        if self._collection is None:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                include=["documents", "metadatas"],
            )
            formatted = []
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                formatted.append({
                    "rank": len(formatted) + 1,
                    "notification_no": meta.get("notification_no", ""),
                    "year": meta.get("year", 0),
                    "equipment": meta.get("equipment", ""),
                    "plant": meta.get("plant", ""),
                    "priority": meta.get("priority", ""),
                    "text": meta.get("search_text", doc),
                    "similarity_score": 0.5,  # unknown in fallback mode
                    "created_date": meta.get("created_date", ""),
                    "created_by": meta.get("created_by", ""),
                })
            return formatted
        except Exception:
            return []

    def get_equipment_history(
        self,
        equipment: str,
        year_range: Optional[tuple[int, int]] = None,
    ) -> Dict[str, Any]:
        """
        Get a complete QM history for an equipment — all notifications
        sorted by year, with semantic summary.
        """
        results = self.search(
            query=equipment,
            equipment=equipment,
            year_range=year_range,
            top_k=50,
        )

        if not results:
            return {"equipment": equipment, "notifications": [], "count": 0}

        # Group by year
        by_year: Dict[int, List] = {}
        for r in results:
            yr = r["year"]
            if yr not in by_year:
                by_year[yr] = []
            by_year[yr].append(r)

        return {
            "equipment": equipment,
            "year_range": year_range,
            "count": len(results),
            "by_year": {
                str(yr): {"count": len(notifs), "notifications": notifs}
                for yr, notifs in sorted(by_year.items(), reverse=True)
            },
        }

    @property
    def stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        if self._collection is None:
            return {"status": "ChromaDB not initialized"}
        try:
            count = self._collection.count()
            return {
                "collection": self.collection_name,
                "total_chunks": count,
                "embedding_mode": "sentence-transformers" if self._use_transformers else "tfidf-fallback",
                "chroma_dir": str(self.chroma_dir),
            }
        except Exception as e:
            return {"status": f"error: {e}"}
