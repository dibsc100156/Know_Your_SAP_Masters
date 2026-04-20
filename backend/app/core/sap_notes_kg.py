"""
sap_notes_kg.py — SAP Note / OSS Message Knowledge Graph (Priority 8)
=====================================================================
Uses LLM entity extraction to build a cross-document knowledge graph of
SAP operational knowledge (Notes, Errors, Transactions, Solutions).

Architecture:
  SAP Note Text → LLM Extraction (Entities & Relations) → Memgraph → Agent Search

Entities:
  - SAPNote: note_id, title, module
  - ErrorCode: code, symptom, module
  - Transaction: tcode, description
  - Solution: description, action

Relationships:
  - (SAPNote)-[:ADDRESSES]->(ErrorCode)
  - (ErrorCode)-[:SOLVED_BY]->(Solution)
  - (ErrorCode)-[:AFFECTS]->(Transaction)
  - (SAPNote)-[:MENTIONS]->(Transaction)
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
MEMGRAPH_USER = os.getenv("MEMGRAPH_USER", "")
MEMGRAPH_PASS = os.getenv("MEMGRAPH_PASS", "")

class SAPNotesKnowledgeGraph:
    def __init__(self, uri=MEMGRAPH_URI, user=MEMGRAPH_USER, password=MEMGRAPH_PASS):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def _execute_write(self, cypher: str, parameters: dict = None):
        with self.driver.session() as session:
            session.run(cypher, parameters or {})

    def _execute_read(self, cypher: str, parameters: dict = None) -> List[dict]:
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def setup_schema(self):
        indexes = [
            "CREATE INDEX ON :SAPNote(note_id);",
            "CREATE INDEX ON :ErrorCode(code);",
            "CREATE INDEX ON :Transaction(tcode);"
        ]
        for query in indexes:
            try:
                self._execute_write(query)
            except Exception as e:
                pass

    def extract_entities_mock(self, note_text: str) -> Dict[str, Any]:
        """
        Mock LLM extraction since API credits might be depleted.
        In production, this calls OpenAI/Claude with structured output.
        """
        import re
        note_id_match = re.search(r"Note\s+#?(\d+)", note_text, re.IGNORECASE)
        note_id = note_id_match.group(1) if note_id_match else "UNKNOWN"
        
        # Look for explicit error codes like RAISE 033 or FF 753
        error_match = re.search(r"(RAISE\s+\d+|FF\s+\d+|SYSTEM_[A-Z_]+|Error\s+[A-Z0-9\s]+)(?=\s)", note_text)
        error_code = error_match.group(1).strip() if error_match else "UNKNOWN_ERR"
        
        # T-codes like F.01, MIGO, MIRO, OX02
        tcode_match = re.search(r"\b([A-Z][\w.]{1,3}\d{1,2}|MIGO|MIRO|OX02|OBCO)\b", note_text)
        tcode = tcode_match.group(1) if tcode_match else "UNKNOWN_TCODE"
        
        # Clean symptom
        symptom_match = re.search(r"Symptom:\s*(.*?)\n", note_text)
        symptom = symptom_match.group(1) if symptom_match else note_text[:50]
        
        # Clean solution
        sol_match = re.search(r"Solution:\s*(.*?)\n", note_text)
        solution = sol_match.group(1) if sol_match else "Apply note instructions"
        
        return {
            "sap_note": {
                "note_id": note_id,
                "title": f"SAP Note {note_id}",
                "module": "Cross-Application"
            },
            "error_code": {
                "code": error_code,
                "symptom": symptom
            },
            "transaction": {
                "tcode": tcode,
                "description": "Affected Transaction"
            },
            "solution": {
                "description": solution,
                "action": "Configuration / Code Correction"
            }
        }

    def ingest_note_graph(self, extracted_data: Dict[str, Any]):
        cypher = """
        // 1. Merge SAP Note
        MERGE (n:SAPNote {note_id: $note.note_id})
        SET n.title = $note.title, n.module = $note.module
        
        // 2. Merge Error Code
        MERGE (e:ErrorCode {code: $error.code})
        SET e.symptom = $error.symptom
        
        // 3. Merge Transaction
        MERGE (t:Transaction {tcode: $tcode.tcode})
        SET t.description = $tcode.description
        
        // 4. Merge Solution
        MERGE (s:Solution {description: $solution.description})
        SET s.action = $solution.action
        
        // 5. Create Relationships
        MERGE (n)-[:ADDRESSES]->(e)
        MERGE (e)-[:SOLVED_BY]->(s)
        MERGE (e)-[:AFFECTS]->(t)
        MERGE (n)-[:MENTIONS]->(t)
        """
        params = {
            "note": extracted_data.get("sap_note", {}),
            "error": extracted_data.get("error_code", {}),
            "tcode": extracted_data.get("transaction", {}),
            "solution": extracted_data.get("solution", {})
        }
        self._execute_write(cypher, params)
        logger.info(f"Ingested SAP Note {params['note'].get('note_id')} into Knowledge Graph.")

    def search_by_error(self, error_code: str) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (e:ErrorCode {code: $code})
        OPTIONAL MATCH (e)-[:SOLVED_BY]->(s:Solution)
        OPTIONAL MATCH (n:SAPNote)-[:ADDRESSES]->(e)
        OPTIONAL MATCH (e)-[:AFFECTS]->(t:Transaction)
        RETURN e.code AS error, 
               e.symptom AS symptom, 
               collect(DISTINCT s.description) AS solutions,
               collect(DISTINCT n.note_id) AS related_notes,
               collect(DISTINCT t.tcode) AS affected_tcodes
        """
        return self._execute_read(cypher, {"code": error_code})

    def process_raw_note(self, note_text: str):
        extracted = self.extract_entities_mock(note_text)
        self.ingest_note_graph(extracted)

# Singleton
_sap_notes_kg = None
def get_sap_notes_kg() -> SAPNotesKnowledgeGraph:
    global _sap_notes_kg
    if _sap_notes_kg is None:
        _sap_notes_kg = SAPNotesKnowledgeGraph()
    return _sap_notes_kg