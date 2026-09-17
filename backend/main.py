from __future__ import annotations

import asyncio
import math
import os
from datetime import date, datetime
from enum import Enum
from time import perf_counter
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from jobspy import scrape_jobs


SUPPORTED_SITES = {"linkedin", "indeed", "google", "zip_recruiter", "glassdoor"}


class JobSearchRequest(BaseModel):
    sites: list[str] = Field(default_factory=lambda: ["linkedin"], min_length=1, max_length=3)
    search_term: str = Field(alias="searchTerm", min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=160)
    results_wanted: int = Field(default=5, alias="resultsWanted", ge=1, le=25)
    hours_old: int | None = Field(default=72, alias="hoursOld", ge=1, le=720)
    remote_only: bool = Field(default=False, alias="remoteOnly")
    fetch_descriptions: bool = Field(default=False, alias="fetchDescriptions")
    country_indeed: str = Field(default="India", alias="countryIndeed")

    model_config = {"populate_by_name": True}

    @field_validator("sites")
    @classmethod
    def validate_sites(cls, sites: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(site.strip().lower() for site in sites))
        unsupported = set(normalized) - SUPPORTED_SITES
        if unsupported:
            raise ValueError(f"Unsupported sites: {', '.join(sorted(unsupported))}")
        return normalized


class JobResult(BaseModel):
    id: str | None = None
    site: str
    title: str
    company: str | None = None
    location: str | None = None
    date_posted: str | None = Field(default=None, alias="datePosted")
    job_url: str = Field(alias="jobUrl")
    direct_url: str | None = Field(default=None, alias="directUrl")
    description: str | None = None
    is_remote: bool | None = Field(default=None, alias="isRemote")
    job_type: str | None = Field(default=None, alias="jobType")

    model_config = {"populate_by_name": True}


class JobSearchResponse(BaseModel):
    jobs: list[JobResult]
    result_count: int = Field(alias="resultCount")
    searched_sites: list[str] = Field(alias="searchedSites")
    duration_ms: int = Field(alias="durationMs")

    model_config = {"populate_by_name": True}


app = FastAPI(title="JobSpy Search API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *[origin.strip().rstrip("/") for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def run_search(request: JobSearchRequest) -> list[JobResult]:
    frame = scrape_jobs(
        site_name=request.sites,
        search_term=request.search_term,
        google_search_term=f"{request.search_term} jobs near {request.location}",
        location=request.location,
        results_wanted=request.results_wanted,
        hours_old=request.hours_old,
        is_remote=request.remote_only,
        linkedin_fetch_description=request.fetch_descriptions,
        country_indeed=request.country_indeed,
        verbose=1,
    )

    results: list[JobResult] = []
    for row in frame.to_dict(orient="records"):
        results.append(
            JobResult(
                id=json_value(row.get("id")),
                site=str(json_value(row.get("site")) or "unknown"),
                title=str(json_value(row.get("title")) or "Untitled role"),
                company=json_value(row.get("company")),
                location=json_value(row.get("location")),
                datePosted=json_value(row.get("date_posted")),
                jobUrl=str(json_value(row.get("job_url")) or ""),
                directUrl=json_value(row.get("job_url_direct")),
                description=json_value(row.get("description")),
                isRemote=json_value(row.get("is_remote")),
                jobType=json_value(row.get("job_type")),
            )
        )
    return results


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "jobspy-api"}


@app.post("/api/jobs/search", response_model=JobSearchResponse)
async def search_jobs(request: JobSearchRequest) -> JobSearchResponse:
    started = perf_counter()
    try:
        jobs = await asyncio.to_thread(run_search, request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Job search failed: {exc}") from exc

    return JobSearchResponse(
        jobs=jobs,
        resultCount=len(jobs),
        searchedSites=request.sites,
        durationMs=round((perf_counter() - started) * 1000),
    )
