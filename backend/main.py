from __future__ import annotations

import asyncio
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from enum import Enum
from time import perf_counter
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from jobspy import scrape_jobs


SUPPORTED_SITES = {"linkedin", "indeed", "google", "zip_recruiter", "glassdoor", "naukri"}


class JobSearchRequest(BaseModel):
    sites: list[str] = Field(default_factory=lambda: ["linkedin"], min_length=1, max_length=len(SUPPORTED_SITES))
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
    failed_sites: list[str] = Field(default_factory=list, alias="failedSites")
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


def run_search(request: JobSearchRequest) -> tuple[list[JobResult], list[str]]:
    def scrape_site(site: str) -> pd.DataFrame:
        return scrape_jobs(
            site_name=site,
            search_term=request.search_term,
            location=request.location,
            results_wanted=request.results_wanted,
            hours_old=request.hours_old,
            is_remote=request.remote_only,
            linkedin_fetch_description=request.fetch_descriptions,
            country_indeed=request.country_indeed,
            verbose=1,
        )

    if len(request.sites) == 1:
        frames = {request.sites[0]: scrape_site(request.sites[0])}
        failed_sites: list[str] = []
    else:
        frames = {}
        failed_sites = []
        with ThreadPoolExecutor(max_workers=min(len(request.sites), 3)) as executor:
            futures = {executor.submit(scrape_site, site): site for site in request.sites}
            for future in as_completed(futures):
                site = futures[future]
                try:
                    frames[site] = future.result()
                except Exception:
                    logging.exception("Job search failed for %s", site)
                    failed_sites.append(site)
        failed_sites.sort(key=request.sites.index)
        if len(failed_sites) == len(request.sites):
            raise RuntimeError("All selected sources failed. Please try one source at a time.")

    results: list[JobResult] = []
    for site in request.sites:
        if site not in frames:
            continue
        for row in frames[site].to_dict(orient="records"):
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
    return results, failed_sites


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "jobspy-api"}


@app.post("/api/jobs/search", response_model=JobSearchResponse)
async def search_jobs(request: JobSearchRequest) -> JobSearchResponse:
    started = perf_counter()
    try:
        jobs, failed_sites = await asyncio.to_thread(run_search, request)
    except Exception as exc:
        if request.sites == ["google"] and "429" in str(exc):
            detail = "Google Jobs is rate limiting this server. Try another source later."
        elif request.sites == ["naukri"] and "CAPTCHA" in str(exc):
            detail = "Naukri requires CAPTCHA verification and cannot be searched from this server right now."
        else:
            detail = "Job search failed. Please try again later."
        raise HTTPException(status_code=502, detail=detail) from exc

    return JobSearchResponse(
        jobs=jobs,
        resultCount=len(jobs),
        searchedSites=request.sites,
        failedSites=failed_sites,
        durationMs=round((perf_counter() - started) * 1000),
    )
