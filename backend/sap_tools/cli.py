#!/usr/bin/env python3
"""
sap_tools.cli -- SAP Masters Agentic RAG CLI

Unified command-line interface for the 5-Pillar RAG system.
Routes to individual tools based on the first argument (slash command).

Usage:
    python -m sap_tools              # Show help
    python -m sap_tools /ddic        # Schema lookup
    python -m sap_tools /sql-pattern # SQL pattern lookup
    python -m sap_tools /graph       # Graph traversal
    python -m sap_tools /validate    # SQL validation
    python -m sap_tools /execute     # SQL execution
    python -m sap_tools /mask        # Result masking
    python -m sap_tools /roles       # Show all roles
    python -m sap_tools /domains     # Show all domains
    python -m sap_tools /info        # Role details
    python -m sap_tools /init        # Initialize all stores
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


HELP_TEXT = """
[SAP Masters Agentic RAG CLI]

Usage: python -m sap_tools <command> [options]

Commands:
  /ddic <query>              [Pillar 3] Schema RAG - Find SAP tables
  /sql-pattern <query>        [Pillar 4] SQL RAG - Find proven SQL templates
  /graph <table_a> <table_b> [Pillar 5] Graph RAG - Find JOIN path
  /validate <sql>             [Security] Validate SQL for safety & access
  /execute <sql>              [Execution] Execute SQL (dry-run by default)
  /mask <json>               [Pillar 1] Apply role-based column masking
  /roles                      Show all available roles
  /domains                    Show all available domains
  /info <role>                Show detailed info for a role
  /init                       Initialize Qdrant/Chroma stores

Options:
  --role <name>               Apply role context (AP_CLERK, CFO_GLOBAL, etc.)
  --domain <name>             Filter by domain
  --n <num>                   Number of results
  --json                      Output as JSON
  --dry-run                   Execute validation only (no real DB)

Examples:
  python -m sap_tools /ddic "find vendor tables" --role AP_CLERK
  python -m sap_tools /sql-pattern "open purchase orders" --n 3
  python -m sap_tools /graph LFA1 MARA --format join
  python -m sap_tools /validate --sql "SELECT * FROM LFA1 WHERE MANDT='100'" --role AP_CLERK
  python -m sap_tools /execute "SELECT EBELN FROM EKKO" --role PROCUREMENT_MANAGER_EU
  echo "{\"BANKN\": \"123\"}" | python -m sap_tools /mask --role AP_CLERK

Roles:
  AP_CLERK, PROCUREMENT_MANAGER_EU, CFO_GLOBAL, HR_ADMIN

Domains:
  business_partner, material_master, purchasing, sales_distribution,
  warehouse_management, quality_management, project_system,
  transportation, customer_service, ehs, variant_configuration,
  real_estate, gts, is_oil, is_retail, is_utilities, is_health,
  taxation_india
"""

ROLES_HELP = """
[Available SAP Roles]

  AP_CLERK                   Accounts Payable - US only (BUKRS: 1000, 1010 | Bank/Tax masked)
  PROCUREMENT_MANAGER_EU     Procurement - EU only (BUKRS: 2000, 2010 | Unmasked)
  CFO_GLOBAL                 Finance - Global unrestricted (BUKRS: * | Unmasked)
  HR_ADMIN                   HR - No procurement access (denied: EKKO, EKPO, BSEG)

Run: python -m sap_tools /info AP_CLERK
"""

DOMAINS_HELP = """
[Available SAP Master Data Domains]

  business_partner           LFA1, KNA1, BUT000, ADRC
  material_master            MARA, MARC, MARD, MAKT, MBEW
  purchasing                 EKKO, EKPO, EINA, EINE, EORD
  sales_distribution         VBAK, VBAP, KNA1, KONP
  warehouse_management       LAGP, LQUA, LEU4
  quality_management         QALS, QAVE, MAPL, PLMK
  project_system             PROJ, PRPS, AFVC
  transportation             VTTK, VTLP, /SCMTMS/*
  customer_service           ASMD, BGMK, VBAK-CS
  ehs                        ESTRH, ESTVH, DGTMD
  variant_configuration      CABN, KLAH, CUOBJ
  real_estate                VICNCN, VIBDAO, VIBDRO
  gts                        /SAPSLL/PNTPR, /SAPSLL/PR
  is_oil                     OIB_A04, OIG_V, T8JV
  is_retail                  MARA-RETAIL, T001W, WRS1
  is_utilities               EGERR, EANL, EVBS
  is_health                  NPAT, NBEW, NPNZ
  taxation_india              J_1IG_HSN_SAC, J_1BBRANCH
"""


def show_info(role: str):
    """Show detailed info for a specific role."""
    from app.core.security import SAP_ROLES

    if role not in SAP_ROLES:
        print(f"[ERROR] Unknown role: {role}")
        print("   Available: AP_CLERK, PROCUREMENT_MANAGER_EU, CFO_GLOBAL, HR_ADMIN")
        return 1

    ctx = SAP_ROLES[role]
    print(f"\n{'=' * 60}")
    print(f"  Role: {ctx.role_id}")
    print(f"{'=' * 60}")
    print(f"  Description: {ctx.description}")
    print(f"\n  Allowed Company Codes: {', '.join(ctx.allowed_company_codes)}")
    print(f"  Allowed Purchasing Orgs: {', '.join(ctx.allowed_purchasing_orgs) or '(none)'}")
    print(f"  Allowed Plants: {', '.join(ctx.allowed_plants)}")
    print(f"\n  Denied Tables ({len(ctx.denied_tables)}):")
    for t in ctx.denied_tables:
        print(f"    - {t}")
    print(f"\n  Masked Fields ({len(ctx.masked_fields)}):")
    if ctx.masked_fields:
        for f in ctx.masked_fields:
            print(f"    - {f}")
    else:
        print("    (none -- fully visible)")
    print(f"\n{'=' * 60}")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "/help"):
        print(HELP_TEXT)
        return 0

    command = sys.argv[1]
    rest_args = sys.argv[2:]

    if command == "/ddic":
        from sap_tools import ddic
        sys.argv = ["ddic"] + rest_args
        return ddic.main()

    elif command == "/sql-pattern":
        from sap_tools import sql_pattern
        sys.argv = ["sql_pattern"] + rest_args
        return sql_pattern.main()

    elif command == "/graph":
        from sap_tools import graph
        sys.argv = ["graph"] + rest_args
        return graph.main()

    elif command == "/validate":
        from sap_tools import validate
        sys.argv = ["validate"] + rest_args
        return validate.main()

    elif command == "/execute":
        from sap_tools import execute
        sys.argv = ["execute"] + rest_args
        return execute.main()

    elif command == "/mask":
        from sap_tools import mask
        sys.argv = ["mask"] + rest_args
        return mask.main()

    elif command == "/roles":
        print(ROLES_HELP)
        return 0

    elif command == "/domains":
        print(DOMAINS_HELP)
        return 0

    elif command == "/info":
        if not rest_args:
            print("[ERROR] /info requires a role argument.")
            print("   python -m sap_tools /info AP_CLERK")
            return 1
        return show_info(rest_args[0])

    elif command == "/init":
        print("\n[INIT] Initializing all RAG stores...")
        try:
            from app.core.vector_store import store_manager, init_vector_store
            from app.core.sql_vector_store import SQLRAGStore
            print("   Initializing Qdrant (Schema + SQL RAG)...")
            init_vector_store()
            print("   Initializing ChromaDB (SQL patterns)...")
            sql_store = SQLRAGStore(db_path="./chroma_db", collection_name="sap_sql_patterns")
            sql_store.initialize_library()
            print("\n   [OK] All stores initialized successfully!")
        except Exception as e:
            print(f"\n   [ERROR] Initialization failed: {e}")
            print("   Make sure you're in the backend/ directory and .venv is activated.")
            return 1
        return 0

    elif command == "/agent":
        print("\n[AGENT] Starting Agentic RAG Orchestrator...")
        try:
            from app.agents.orchestrator import run_agent_loop
            from app.core.security import security_mesh
        except Exception as e:
            print(f"\n   [ERROR] Could not load orchestrator: {e}")
            return 1

        # Extract agent arguments from rest_args
        query_parts = []
        role = "AP_CLERK"
        domain = "auto"
        verbose = False

        i = 0
        while i < len(rest_args):
            arg = rest_args[i]
            if arg == "--role" and i + 1 < len(rest_args):
                role = rest_args[i + 1]
                i += 2
            elif arg == "--domain" and i + 1 < len(rest_args):
                domain = rest_args[i + 1]
                i += 2
            elif arg == "--verbose":
                verbose = True
                i += 1
            elif not arg.startswith("--"):
                query_parts.append(arg)
                i += 1
            else:
                i += 1

        query = " ".join(query_parts)
        if not query:
            print("[ERROR] /agent requires a query. Usage: python -m sap_tools /agent \"your question\" --role AP_CLERK")
            return 1

        try:
            auth_context = security_mesh.get_context(role)
        except Exception:
            print(f"[ERROR] Unknown role: {role}")
            return 1

        result = run_agent_loop(
            query=query,
            auth_context=auth_context,
            domain=domain,
            verbose=verbose,
        )

        print("\n" + "=" * 60)
        print("  AGENT RESULT")
        print("=" * 60)
        print(f"\n  Answer: {result['answer']}")
        print(f"\n  SQL:\n  {result['executed_sql']}")
        if result.get("masked_fields"):
            print(f"\n  Masked: {result['masked_fields']}")
        print(f"\n  Execution: {result['execution_time_ms']}ms | {len(result['tool_trace'])} tools")
        print("=" * 60)
        return 0

    elif command == "/tools":
        try:
            from app.agents.orchestrator_tools import list_tools
            tools = list_tools()
            print(f"\n[TOOLS] Available tools ({len(tools)}):")
            for t in tools:
                print(f"\n  [{t['name']}] {t['pillars']}")
                print(f"    {t['description'][:80]}...")
        except Exception as e:
            print(f"[ERROR] {e}")
            return 1
        return 0

    else:
        print(f"[ERROR] Unknown command: {command}")
        print("   Run: python -m sap_tools --help")
        return 1


if __name__ == "__main__":
    sys.exit(main())
