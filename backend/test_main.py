from fastapi.testclient import TestClient
import pandas as pd
import pytest

import backend.main as main
import jobspy.naukri as naukri
from jobspy.exception import NaukriException
from jobspy.model import ScraperInput, Site


client = TestClient(main.app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jobspy-api"}


def test_search_response(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "run_search",
        lambda request: (
            [
                main.JobResult(
                    id="li-123",
                    site="linkedin",
                    title="Full Stack Developer",
                    company="Example Company",
                    location="Bengaluru, India",
                    datePosted="2026-09-15",
                    jobUrl="https://www.linkedin.com/jobs/view/123",
                    directUrl=None,
                    isRemote=False,
                )
            ],
            [],
        ),
    )

    response = client.post(
        "/api/jobs/search",
        json={
            "sites": ["linkedin"],
            "searchTerm": "full stack developer",
            "location": "Bengaluru, India",
            "resultsWanted": 5,
            "hoursOld": 72,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resultCount"] == 1
    assert payload["jobs"][0]["jobUrl"].endswith("/123")


def test_rejects_unknown_source() -> None:
    response = client.post(
        "/api/jobs/search",
        json={
            "sites": ["unknown"],
            "searchTerm": "developer",
            "location": "Bengaluru, India",
        },
    )

    assert response.status_code == 422


def test_all_sources_include_naukri_and_keep_google_filters(monkeypatch) -> None:
    captured = []

    def fake_scrape_jobs(**kwargs):
        captured.append(kwargs)
        site = kwargs["site_name"]
        if site == "google":
            raise RuntimeError("Google rate limited")
        return pd.DataFrame([{"site": site, "title": "Engineer", "job_url": f"https://example.com/{site}"}])

    monkeypatch.setattr(main, "scrape_jobs", fake_scrape_jobs)
    sites = ["linkedin", "indeed", "google", "zip_recruiter", "glassdoor", "naukri"]
    response = client.post(
        "/api/jobs/search",
        json={
            "sites": sites,
            "searchTerm": "software engineer",
            "location": "Bengaluru, India",
            "resultsWanted": 5,
            "hoursOld": 24,
            "remoteOnly": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["searchedSites"] == sites
    assert response.json()["resultCount"] == 5
    assert response.json()["jobs"][-1]["site"] == "naukri"
    assert response.json()["failedSites"] == ["google"]
    assert {kwargs["site_name"] for kwargs in captured} == set(sites)
    assert all(kwargs["hours_old"] == 24 and kwargs["is_remote"] is True for kwargs in captured)
    assert all("google_search_term" not in kwargs for kwargs in captured)


def test_naukri_captcha_is_not_reported_as_empty_results(monkeypatch) -> None:
    class BlockedSession:
        headers = {}

        def get(self, *args, **kwargs):
            return type("Response", (), {"status_code": 406, "text": '{"message":"recaptcha required"}'})()

    monkeypatch.setattr(naukri, "create_session", lambda **kwargs: BlockedSession())

    with pytest.raises(NaukriException, match="CAPTCHA"):
        naukri.Naukri().scrape(
            ScraperInput(site_type=[Site.NAUKRI], search_term="engineer", results_wanted=1)
        )
