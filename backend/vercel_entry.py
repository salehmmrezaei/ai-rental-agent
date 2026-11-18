"""Public-only Vercel ASGI entrypoint. No migration/seed/network calls on import."""
import os

# These are security invariants for this entrypoint, not operator preferences.
os.environ.update(PUBLIC_DEMO_MODE='true', DEMO_STATE_BACKEND='postgres',
    SERVERLESS_DATABASE='true', ASSISTANT_ENABLED='false', OPENAI_API_KEY='',
    PUBLIC_DOCS_ENABLED='false', UPLOAD_DIR='/tmp/casa-uploads')

from app.config import get_settings
get_settings.cache_clear()
from app.main import create_app
app = create_app()
