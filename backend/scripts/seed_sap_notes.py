import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.sap_notes_kg import get_sap_notes_kg

def seed_knowledge_graph():
    kg = get_sap_notes_kg()
    kg.setup_schema()

    mock_notes = [
        """SAP Note 2345678
        Title: Company code not found
        Symptom: When running F.01, you receive error RAISE 033 indicating missing company code.
        Solution: Create company code in T001 via transaction OX02.
        """,
        """SAP Note 1234567
        Title: Dump in MIGO
        Symptom: Short dump Error SYSTEM_CORE_DUMPed in MIGO when posting goods receipt.
        Solution: Apply code correction attached to this note. Update table MSEG.
        """,
        """SAP Note 3456789
        Title: Missing tax jurisdiction code
        Symptom: Error FF 753 during invoice verification in MIRO.
        Solution: Maintain tax jurisdiction code in table TTXD using OBCO.
        """
    ]

    print("Extracting and ingesting SAP Notes into Memgraph...")
    for text in mock_notes:
        extracted = kg.extract_entities_mock(text)
        print(f" Extracted: {extracted['sap_note']['note_id']} - Error: {extracted['error_code']['code']}")
        kg.ingest_note_graph(extracted)

    print("\n--- Testing Search ---")
    results = kg.search_by_error("RAISE 033")
    print(f"Search for 'RAISE 033': {results}")

    results = kg.search_by_error("FF 753")
    print(f"Search for 'FF 753': {results}")

    kg.close()

if __name__ == "__main__":
    seed_knowledge_graph()