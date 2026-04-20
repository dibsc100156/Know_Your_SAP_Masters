import re

filepath = "app/agents/orchestrator.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Fix self_critique execution block.
# Right now it's:
#     if not should_run_step("self_critique", {"confidence": 0.50}): # Mock confidence
#         logger.info("[4.5/5] [Phase 4] Self-Critique — SKIPPED (high confidence)")
#         critique_result = {"passed": True, "score": 7, "issues": []}
#     else:
#         logger.info("\n[4.5/5] [Phase 4] Self-Critique — critique_agent.critique()")
#
#     # Initialize heal_info upfront
#     ...
#     critique_result = critique_agent.critique(

# We want to change the whole section.
# First, let's revert the previous change to make it easier to replace.
old_broken = """    # Priority 10: evaluate fluent step condition for self_critique
    if not should_run_step("self_critique", {"confidence": 0.50}): # Mock confidence
        logger.info("[4.5/5] [Phase 4] Self-Critique — SKIPPED (high confidence)")
        critique_result = {"passed": True, "score": 7, "issues": []}
    else:
        logger.info("\\n[4.5/5] [Phase 4] Self-Critique"""

new_fixed = """        logger.info("\\n[4.5/5] [Phase 4] Self-Critique"""

# Let's see if we can find old_broken in content
if old_broken in content:
    content = content.replace(old_broken, new_fixed, 1)

# Now, find the actual self critique execution block
# We want to wrap the `critique_result = critique_agent.critique(...)` up to `trace(...)`
# Actually, an easier way is to just do:
# if not should_run_step("self_critique", {"confidence": 0.50}):
#     critique_result = {"passed": True, "score": 7, "issues": []}
# else:
#     critique_result = critique_agent.critique(...)
#     trace(...)

old_execution = """    critique_result = critique_agent.critique(

        query=query,

        sql=generated_sql,

        schema_context=schema_context,

        auth_context={

            "role_id": auth_context.role_id,

            "filters": auth_context.get_where_clauses() if hasattr(auth_context, "get_where_clauses") else {},

            "allowed_company_codes": auth_context.allowed_company_codes,

            "allowed_plants": auth_context.allowed_plants,

            "allowed_purchasing_orgs": auth_context.allowed_purchasing_orgs,

            "allowed_sales_orgs": auth_context.allowed_sales_orgs,

        }

    )

    

    trace("critique_agent", ToolResult(

        status=ToolStatus.SUCCESS if critique_result["passed"] else ToolStatus.ERROR,

        message=f"Score: {critique_result['score']} — {'PASS' if critique_result['passed'] else 'FAIL'}",

        data=critique_result,

        metadata={},

    ))"""

new_execution = """    # Priority 10: Fluent Orchestrator - evaluate self_critique condition
    if not should_run_step("self_critique", {"confidence": 0.50}): # Mock confidence 0.50 for now
        logger.info("[4.5/5] [Phase 4] Self-Critique — SKIPPED (fluent step condition)")
        critique_result = {"passed": True, "score": 7, "issues": []}
    else:
        critique_result = critique_agent.critique(
            query=query,
            sql=generated_sql,
            schema_context=schema_context,
            auth_context={
                "role_id": auth_context.role_id,
                "filters": auth_context.get_where_clauses() if hasattr(auth_context, "get_where_clauses") else {},
                "allowed_company_codes": auth_context.allowed_company_codes,
                "allowed_plants": auth_context.allowed_plants,
                "allowed_purchasing_orgs": auth_context.allowed_purchasing_orgs,
                "allowed_sales_orgs": auth_context.allowed_sales_orgs,
            }
        )
        
        trace("critique_agent", ToolResult(
            status=ToolStatus.SUCCESS if critique_result["passed"] else ToolStatus.ERROR,
            message=f"Score: {critique_result['score']} — {'PASS' if critique_result['passed'] else 'FAIL'}",
            data=critique_result,
            metadata={},
        ))"""

if old_execution in content:
    content = content.replace(old_execution, new_execution, 1)
    print("Fixed execution wrapping for self_critique")
else:
    print("Could not find old_execution")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
