"""FastAPI application entry point for ClinTrace AI."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, settings
from app.routers import health, auth, patients, doctors, documents, analysis, consent, reviews, audit





FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ensure private storage directories exist on startup and seed demo data in dev."""
    settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.APP_ENV != "production":
        from app.utils.seed_demo import seed_demo_data
        seed_demo_data()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Clinical intelligence decision-support prototype for reconstructing "
        "patient medical history from scattered records."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(doctors.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(consent.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(audit.router, prefix="/api")

# Explicit routes for root HTML pages
@app.get("/", include_in_schema=False)
def serve_landing_page() -> FileResponse:
    """Serve the frontend landing page."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/login.html", include_in_schema=False)
def serve_login_page() -> FileResponse:
    """Serve the login page."""
    return FileResponse(str(FRONTEND_DIR / "login.html"))


@app.get("/signup.html", include_in_schema=False)
def serve_signup_page() -> FileResponse:
    """Serve the registration page."""
    return FileResponse(str(FRONTEND_DIR / "signup.html"))


# Serve subdirectories for static CSS, JS, Patient and Doctor pages
if (FRONTEND_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
if (FRONTEND_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
if (FRONTEND_DIR / "patient").exists():
    app.mount("/patient", StaticFiles(directory=str(FRONTEND_DIR / "patient"), html=True), name="patient")
if (FRONTEND_DIR / "doctor").exists():
    app.mount("/doctor", StaticFiles(directory=str(FRONTEND_DIR / "doctor"), html=True), name="doctor")

