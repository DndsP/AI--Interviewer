from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.interview import router as interview_router
from app.core.config import get_settings
from app.core.database import Base, engine


settings = get_settings()
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(Path("app") / "static")), name="static")
app.include_router(interview_router)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html = Path("app") / "templates" / "index.html"
    return HTMLResponse(html.read_text(encoding="utf-8"))
