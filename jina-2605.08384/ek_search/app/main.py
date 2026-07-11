"""Entry point — run with: uvicorn app.main:app --reload --port 8000"""
import uvicorn
from app.api import app
from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host=s.api_host, port=s.api_port, reload=True, log_level=s.log_level.lower())
