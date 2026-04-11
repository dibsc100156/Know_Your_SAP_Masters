from app.main import app
print('FastAPI:', app.title)
print('Routes:', [r.path for r in app.routes][:10])
