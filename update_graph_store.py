import re

graph_store_path = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\graph_store.py"
with open(graph_store_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add nodes for the new domains
new_nodes = '''
        # --- NEW DOMAINS ---
        self.add_node(SAPGraphNode("KONP", "Table", {"domain": "sales_distribution", "desc": "Pricing Conditions"}))
        self.add_node(SAPGraphNode("LAGP", "Table", {"domain": "warehouse_management", "desc": "Storage Bins"}))
        self.add_node(SAPGraphNode("MAPL", "Table", {"domain": "quality_management", "desc": "Inspection Plans"}))
        self.add_node(SAPGraphNode("PRPS", "Table", {"domain": "project_system", "desc": "WBS Elements"}))
        self.add_node(SAPGraphNode("VTTK", "Table", {"domain": "transportation", "desc": "Shipment Header"}))
        self.add_node(SAPGraphNode("ASMD", "Table", {"domain": "customer_service", "desc": "Service Master"}))
        self.add_node(SAPGraphNode("ESTRH", "Table", {"domain": "ehs", "desc": "Substance Data"}))
        self.add_node(SAPGraphNode("CABN", "Table", {"domain": "variant_configuration", "desc": "Characteristics"}))
        self.add_node(SAPGraphNode("VICNCN", "Table", {"domain": "real_estate", "desc": "Real Estate Contract"}))
        self.add_node(SAPGraphNode("SAPSLL_PNTPR", "Table", {"domain": "gts", "desc": "Sanctioned Party Lists"}))
        self.add_node(SAPGraphNode("OIB_A04", "Table", {"domain": "is_oil", "desc": "Silo/Tank Data"}))
        self.add_node(SAPGraphNode("WRS1", "Table", {"domain": "is_retail", "desc": "Assortment"}))
        self.add_node(SAPGraphNode("EGERR", "Table", {"domain": "is_utilities", "desc": "Device Locations"}))
        self.add_node(SAPGraphNode("NPAT", "Table", {"domain": "is_health", "desc": "Patients"}))
        self.add_node(SAPGraphNode("J_1IG_HSN_SAC", "Table", {"domain": "taxation_india", "desc": "HSN/SAC Codes"}))

        # Example connections to existing structures (dummy relationships)
        self.add_edge(SAPGraphEdge("MARA", "KONP", "PRICED_BY"))
        self.add_edge(SAPGraphEdge("MARA", "LAGP", "STORED_IN"))
        self.add_edge(SAPGraphEdge("MARA", "MAPL", "INSPECTED_BY"))
'''

content = content.replace("        self.add_node(SAPGraphNode(\"MARA\", \"Table\", {\"domain\": \"material_master\", \"desc\": \"General Material Data\"}))",
                          "        self.add_node(SAPGraphNode(\"MARA\", \"Table\", {\"domain\": \"material_master\", \"desc\": \"General Material Data\"}))" + new_nodes)

with open(graph_store_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Graph store updated.")
