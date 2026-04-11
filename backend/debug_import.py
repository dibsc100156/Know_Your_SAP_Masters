import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
sys.stdout.reconfigure(encoding='utf-8')

from celery import Celery
import os

_rabbitmq_pass = os.environ.get('RABBITMQ_PASS', 'sapmasters123')
_broker_url = os.environ.get('CELERY_BROKER_URL', f'amqp://sapmasters:{_rabbitmq_pass}@rabbitmq:5672//')
_result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

app = Celery('sap_masters', broker=_broker_url, backend=_result_backend)
app.set_current()

print('Before orchestrator_tasks import:')
app_mod = sys.modules.get('app')
print('  sys.modules["app"]:', type(app_mod), app_mod)

import app.workers.orchestrator_tasks

print('After orchestrator_tasks import:')
app_mod2 = sys.modules.get('app')
print('  sys.modules["app"]:', type(app_mod2), app_mod2)
print('  app is sys.modules["app"]:', app is app_mod2)
print('  type(app):', type(app))
print('  app:', app)
