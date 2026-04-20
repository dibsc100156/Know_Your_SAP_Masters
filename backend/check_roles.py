import sys, re
with open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\security.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
roles = re.findall(r'"(\w+)"\s*:', content)
print('Roles found:', sorted(set(roles))[:30])
# Also check Redis usage
redis_patterns = re.findall(r'redis.*?get|set|delete', content[:5000])
print('Redis patterns:', redis_patterns[:5])