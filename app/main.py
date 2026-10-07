"""KAY AI MOVIE RECAP — FastAPI application entrypoint."""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import settings
from .routers import auth, projects, ingest, segments, pipeline, tts_api, admin

app = FastAPI(title="KAY AI Movie Recap", version="1.0.0")

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"


@app.on_event("startup")
def startup():
    db.init_db()
    # ensure first admin exists
    from .security import hash_password
    conn = db.get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE username=?",
                           (settings.ADMIN_USERNAME,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users(username, password_hash, is_admin, credits, created_at)"
                " VALUES (?,?,?,?,?)",
                (settings.ADMIN_USERNAME, hash_password(settings.ADMIN_PASSWORD),
                 1, 100000, db.now_ms()))
            conn.commit()
            print(f"[kay] admin user created: {settings.ADMIN_USERNAME}")
    finally:
        conn.close()


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(ingest.router)
app.include_router(segments.router)
app.include_router(pipeline.router)
app.include_router(tts_api.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"ok": True, "name": "KAY AI Movie Recap"}


# ---- frontend (static SPA) ----
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(FRONTEND / "index.html"))


def main():
    import uvicorn
    uvicorn.run("app.main:app",
                host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
