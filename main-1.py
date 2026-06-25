from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from database import create_tables
from routers import auth, tutors, bookings, ai_proxy, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield

app = FastAPI(
    title="TutorGate AI API",
    description="Backend API for TutorGate AI — Africa's Trusted Learning Marketplace",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your Netlify URLs in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,     prefix="/api/auth",     tags=["Auth"])
app.include_router(tutors.router,   prefix="/api/tutors",   tags=["Tutors"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["Bookings"])
app.include_router(ai_proxy.router, prefix="/api/ai",       tags=["AI Assistant"])
app.include_router(admin.router,    prefix="/api/admin",    tags=["Admin"])

@app.get("/")
def root():
    return {"status": "TutorGate API is running 🎓", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}
