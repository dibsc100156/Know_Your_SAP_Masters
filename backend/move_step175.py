"""Move Step 1.75 out of the 'if not meta_path_used' block to after it ends."""

with open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\orchestrator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the Step 1.75 block boundaries (at 8 spaces inside the if-block)
# It starts at "        # STEP 1.75:" and ends at "        # STEP 2:" 
# We need to DEDENT the entire block by 4 spaces (8->4)

step_175_start = None
step_175_end = None
step_2_start = None

for i, line in enumerate(lines):
    stripped = line.rstrip()
    if not stripped:
        continue
    # Find dedent target: "        # STEP 2: SQL PATTERN RETRIEVAL" at 8 spaces
    if stripped.startswith('# STEP 2: SQL PATTERN RETRIEVAL (Pillar 4)'):
        step_2_start = i
        break

# The Step 1.75 block goes from its first content line to just before STEP 2
# Let's find it by looking for the "# STEP 1.75:" comment at 8 spaces
in_step175 = False
step175_lines = []
for i, line in enumerate(lines):
    stripped = line.rstrip()
    if not stripped:
        step175_lines.append((i, line))
        continue
    indent = len(line) - len(line.lstrip())
    if stripped.startswith('# STEP 1.75:') and indent == 8:
        in_step175 = True
        step_175_start = i
    if in_step175:
        step175_lines.append((i, line))
        if stripped.startswith('# STEP 2:') and indent == 8:
            step_175_end = i
            break

print(f"Step 1.75 block: lines {step_175_start+1}-{step_175_end} ({len(step175_lines)} lines)")

# Also find where to insert the initialization of qm_semantic_results
# Before "    if not meta_path_used:" (find it at 4 spaces)
init_insert_line = None
for i, line in enumerate(lines):
    stripped = line.rstrip()
    if not stripped:
        continue
    if stripped.startswith('if not meta_path_used:'):
        init_insert_line = i
        break

print(f"if not meta_path_used at line: {init_insert_line+1}")

# Build new content
# 1. Add "    qm_semantic_results: List[Dict[str, Any]] = []" before the if-block
# 2. Dedent Step 1.75 block from 8 spaces to 4 spaces
# 3. Move it to AFTER the if-block (before STEP 4)

# Find the if-block end (last non-empty line before "# STEP 4:" at 4 spaces)
if_block_end = None
for i in range(len(lines)-1, -1, -1):
    stripped = lines[i].rstrip()
    if stripped and not stripped.startswith('#'):
        indent = len(lines[i]) - len(lines[i].lstrip())
        if indent >= 8:
            if_block_end = i
            break

print(f"if-block ends at line: {if_block_end+1}")

# New approach: build the file with Step 1.75 moved to after the if-block
new_lines = []
i = 0
while i < len(lines):
    stripped = lines[i].rstrip()
    indent = len(lines[i]) - len(lines[i].lstrip()) if lines[i].strip() else 0
    
    # Insert qm_semantic_results initialization before "if not meta_path_used"
    if stripped == 'if not meta_path_used:':
        new_lines.append('    qm_semantic_results: List[Dict[str, Any]] = []\n')
        new_lines.append('\n')
        new_lines.append(lines[i])  # the "if not meta_path_used:" line
        i += 1
        # Skip the entire Step 1.75 block (it will be re-inserted after the if-block)
        # Skip until we hit "        # STEP 2:" (at 8 spaces)
        while i < len(lines):
            s = lines[i].rstrip()
            ind = len(lines[i]) - len(lines[i].lstrip()) if lines[i].strip() else 0
            if s.startswith('# STEP 2: SQL PATTERN RETRIEVAL (Pillar 4)') and ind == 8:
                break
            i += 1
        continue
    
    # Skip the Step 1.75 block lines (we'll re-insert after the if-block)
    # Detect: we're in Step 1.75 when we see the dedented comment at 8 spaces
    # OR when we're between Step 1.75 and Step 2
    if i < len(lines):
        s = lines[i].rstrip()
        ind = len(lines[i]) - len(lines[i].lstrip()) if lines[i].strip() else 0
        # Step 1.75 block starts at "        # STEP 1.75:" and ends at "        # STEP 2:"
        if s.startswith('# STEP 1.75:') and ind == 8:
            # Skip all Step 1.75 lines until Step 2
            while i < len(lines):
                s2 = lines[i].rstrip()
                ind2 = len(lines[i]) - len(lines[i].lstrip()) if lines[i].strip() else 0
                if s2.startswith('# STEP 2: SQL PATTERN RETRIEVAL (Pillar 4)') and ind2 == 8:
                    # Don't skip Step 2, let it fall through to normal processing
                    break
                i += 1
            # After skipping Step 1.75 block, add it back here (dedented)
            # Read the Step 1.75 block
            step175_start_i = None
            step175_end_i = None
            for j, ln in enumerate(lines):
                s = ln.rstrip()
                ind = len(ln) - len(ln.lstrip()) if ln.strip() else 0
                if s.startswith('# STEP 1.75:') and ind == 8 and step175_start_i is None:
                    step175_start_i = j
                if step175_start_i is not None and step175_end_i is None:
                    s2 = ln.rstrip()
                    ind2 = len(ln) - len(ln.lstrip()) if ln.strip() else 0
                    if s2.startswith('# STEP 2: SQL PATTERN RETRIEVAL (Pillar 4)') and ind2 == 8:
                        step175_end_i = j
                        break
            # Insert Step 1.75 block with dedented content
            if step175_start_i is not None and step175_end_i is not None:
                new_lines.append('\n')
                new_lines.append('\n')
                for j in range(step175_start_i, step175_end_i):
                    original = lines[j]
                    if original.strip():
                        ind = len(original) - len(original.lstrip())
                        if ind >= 8:  # dedent by 4 spaces
                            new_ind = ind - 4
                            new_lines.append(' ' * new_ind + original.lstrip() + '\n')
                        else:
                            new_lines.append(original)
                    else:
                        new_lines.append(original)
                new_lines.append('\n')
            continue
    
    new_lines.append(lines[i])
    i += 1

with open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\orchestrator.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done. Step 1.75 moved outside the if not meta_path_used block.")
