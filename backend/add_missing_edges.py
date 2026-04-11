"""
add_missing_edges.py — Fix the one-directional edges in Memgraph
The init CQL created LFA1→EINA but not EINA→LFA1.
This script adds the missing reverse-direction edges and any other
gaps to fully mirror the NetworkX graph.
"""
from gqlalchemy import Memgraph

mg = Memgraph(host='127.0.0.1', port=7687)

# Missing edges that are needed for correct BFS traversal
# Format: (from_table, to_table, condition, cardinality, bridge_type, notes)
missing_edges = [
    # LFA1 ↔ EINA (the init CQL only loaded LFA1 → EINA, not EINA → LFA1)
    ("EINA", "LFA1", "EINA.LIFNR = LFA1.LIFNR", "N:1", "cross_module",
     "Purchasing Info Record → Vendor master"),

    # MARA ↔ EKKO (cross-module)
    ("MARA", "EKKO", "MARA.MATNR = EKKO.MATNR", "N:1", "cross_module",
     "Material → PO (material in PO)"),

    # MARA ↔ LQUA
    ("MARA", "LQUA", "MARA.MATNR = LQUA.MATNR", "N:1", "cross_module",
     "Material → WM Quant"),

    # MSLB → LFA1 (vendor special stock → vendor)
    ("MSLB", "LFA1", "MSLB.LIFNR = LFA1.LIFNR", "N:1", "cross_module",
     "Special Stock (vendor-owned) → Vendor master"),

    # LQUA ↔ LAGP
    ("LQUA", "LAGP", "LQUA.MATNR = LAGP.WERKS AND LQUA.LGORT = LAGP.LGTYP", "N:1", "cross_module",
     "WM Quant → Storage Type"),

    # QALS ↔ EKKO
    ("QALS", "EKKO", "QALS.MATNR = EKKO.MATNR", "N:1", "cross_module",
     "QM Inspection Lot → PO"),

    # MKOL ↔ PRPS
    ("MKOL", "PRPS", "MKOL.OBJNR = PRPS.OBJNR", "N:1", "cross_module",
     "Project-owned special stock → WBS Element"),

    # MSKA ↔ KNA1
    ("MSKA", "KNA1", "MSKA.KUNNU = KNA1.KUNNR", "N:1", "cross_module",
     "Sales order stock → Customer owner"),

    # KNA1 ↔ KNB1
    ("KNA1", "KNB1", "KNA1.KUNNR = KNB1.KUNNR", "1:N", "internal",
     "Customer → Customer company-code"),

    # KNA1 ↔ KNVV
    ("KNA1", "KNVV", "KNA1.KUNNR = KNVV.KUNNR", "1:N", "internal",
     "Customer → Customer sales area"),

    # BUT000 ↔ LFA1 (reverse — already have LFA1→BUT000)
    ("LFA1", "BUT000", "LFA1.LIFNR = BUT000.PARTNER", "1:1", "cross_module",
     "Vendor → BP Central (reverse)"),

    # BUT000 ↔ KNA1 (reverse — already have KNA1→BUT000)
    ("LFA1", "KNA1", "LFA1.LIFNR = KNA1.KUNNR", "N:1", "cross_module",
     "Vendor/Customer cross-type query"),

    # MARA ↔ MVKE
    ("MARA", "MVKE", "MARA.MATNR = MVKE.MATNR", "1:N", "internal",
     "Material → Sales org data"),

    # MARA ↔ MCH1
    ("MARA", "MCH1", "MARA.MATNR = MCH1.MATNR", "1:N", "internal",
     "Material → Batch master"),

    # MARA ↔ QALS
    ("MARA", "QALS", "MARA.MATNR = QALS.MATNR", "1:N", "cross_module",
     "Material → QM Inspection Lot"),

    # MARA ↔ MSKA
    ("MARA", "MSKA", "MARA.MATNR = MSKA.MATNR", "1:N", "cross_module",
     "Material → Sales order stock"),

    # MARA ↔ MSLB
    ("MARA", "MSLB", "MARA.MATNR = MSLB.MATNR", "1:N", "cross_module",
     "Material → Special stock (vendor)"),

    # MARA ↔ MKOL
    ("MARA", "MKOL", "MARA.MATNR = MKOL.MATNR", "1:N", "cross_module",
     "Material → Special stock (project)"),

    # T001 ↔ T001W
    ("T001", "T001W", "T001.BUKRS = T001W.WERKS", "1:N", "cross_module",
     "Company Code → Plant"),

    # EKKO ↔ EKES (reverse — already have EKKO → EKES)
    ("EKES", "EKKO", "EKES.EBELN = EKKO.EBELN", "N:1", "internal",
     "Vendor confirmation → PO"),

    # VBAK ↔ VBAK (document flow self-ref)
    ("VBAK", "VBFA", "VBAK.VBELN = VBFA.VBELN", "1:N", "cross_module",
     "Sales order → Document flow"),

    # LIKP ↔ VTTK
    ("LIKP", "VTTK", "LIKP.TKNUM = VTTK.TKNUM", "1:N", "cross_module",
     "Delivery → Transportation order"),

    # VTTK ↔ LFA1 (reverse)
    ("VTTK", "LFA1", "VTTK.LIFNR = LFA1.LIFNR", "N:1", "cross_module",
     "Transportation order → Carrier/Shipper vendor"),

    # QAVE ↔ LFA1
    ("QAVE", "LFA1", "QAVE.LIFNR = LFA1.LIFNR", "N:1", "cross_module",
     "QM Usage Decision → Vendor (quality rating)"),

    # ANEP ↔ ANLA
    ("ANEP", "ANLA", "ANEP.ANLN1 = ANLA.ANLN1 AND ANEP.BUKRS = ANLA.BUKRS", "1:N", "cross_module",
     "Asset line items → Asset master"),
]

errors = []
added = 0
for from_tbl, to_tbl, condition, card, bridge, notes in missing_edges:
    cypher = f"""
    MATCH (a), (b)
    WHERE a.table_name = '{from_tbl}' AND b.table_name = '{to_tbl}'
    AND 'SAPTable' IN labels(a) AND 'SAPTable' IN labels(b)
    MERGE (a)-[r:FOREIGN_KEY]->(b)
    SET r.condition = '{condition}',
        r.cardinality = '{card}',
        r.bridge_type = '{bridge}',
        r.notes = '{notes}'
    """
    try:
        list(mg.execute_and_fetch(cypher))
        added += 1
    except Exception as e:
        errors.append((from_tbl, to_tbl, str(e)[:60]))

print(f"Added: {added} edges")
if errors:
    print(f"Errors ({len(errors)}):")
    for e in errors[:5]:
        print(f"  {e[0]} -> {e[1]}: {e[2]}")
else:
    print("No errors")
