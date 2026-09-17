from fastapi.testclient import TestClient

import backend.main as main


client = TestClient(main.app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jobspy-api"}


def test_search_response(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "run_search",
        lambda request: [
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
