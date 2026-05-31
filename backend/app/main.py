from __future__ import annotations

from fastapi import FastAPI

from backend.app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title=active_settings.app_name)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": active_settings.app_name}

    return app


app = create_app()
