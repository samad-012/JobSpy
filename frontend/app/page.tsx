"use client";

import { FormEvent, useState } from "react";
import { BriefcaseBusiness, ExternalLink, LoaderCircle, MapPin, Search } from "lucide-react";

type Job = {
  id: string | null;
  site: string;
  title: string;
  company: string | null;
  location: string | null;
  datePosted: string | null;
  jobUrl: string;
  directUrl: string | null;
  description: string | null;
  isRemote: boolean | null;
  jobType: string | null;
};

type SearchResponse = {
  jobs: Job[];
  resultCount: number;
  searchedSites: string[];
  failedSites?: string[];
  durationMs: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SEARCH_SITES = ["linkedin", "indeed", "google", "zip_recruiter", "glassdoor", "naukri"];
const SITE_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  indeed: "Indeed",
  google: "Google Jobs",
  zip_recruiter: "ZipRecruiter",
  glassdoor: "Glassdoor",
  naukri: "Naukri",
};

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [summary, setSummary] = useState("");
  const [timeUnit, setTimeUnit] = useState<"hours" | "days">("days");
  const [postedWithin, setPostedWithin] = useState(3);

  async function searchJobs(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setWarning("");
    setSummary("");
    setJobs([]);

    const data = new FormData(event.currentTarget);
    const request = {
      sites: data.get("site") === "all" ? SEARCH_SITES : [data.get("site")],
      searchTerm: data.get("searchTerm"),
      location: data.get("location"),
      resultsWanted: Number(data.get("resultsWanted")),
      hoursOld: timeUnit === "days" ? postedWithin * 24 : postedWithin,
      workMode: data.get("workMode"),
      fetchDescriptions: data.get("fetchDescriptions") === "on",
      countryIndeed: "India",
    };

    try {
      const response = await fetch(`${API_URL}/api/jobs/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "The search could not be completed.");

      const payload = result as SearchResponse;
      setJobs(payload.jobs);
      setSummary(`${payload.resultCount} jobs found in ${(payload.durationMs / 1000).toFixed(1)} seconds`);
      if (payload.failedSites?.length) {
        setWarning(`Some sources could not be searched: ${payload.failedSites.map((site) => SITE_LABELS[site] ?? site).join(", ")}.`);
      }
    } catch (reason) {
      setJobs([]);
      setError(reason instanceof Error ? reason.message : "The search could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand"><BriefcaseBusiness size={20} /> JobSpy Search</div>
        <span className="status"><i /> Retrieval service</span>
      </header>

      <section className="workspace">
        <div className="heading">
          <div>
            <p className="eyebrow">JOB DISCOVERY</p>
            <h1>Find current opportunities</h1>
            <p className="subcopy">Search public listings and open the original job page.</p>
          </div>
        </div>

        <form className="search-panel" onSubmit={searchJobs}>
          <label className="wide">
            <span>Job title or keywords</span>
            <input name="searchTerm" defaultValue="full stack developer" required minLength={2} />
          </label>
          <label className="wide">
            <span>Location</span>
            <input name="location" defaultValue="Bengaluru, Karnataka, India" required minLength={2} />
          </label>
          <label>
            <span>Source</span>
            <select name="site" defaultValue="linkedin">
              <option value="all">All sources</option>
              <option value="linkedin">LinkedIn</option>
              <option value="indeed">Indeed</option>
              <option value="google">Google Jobs</option>
              <option value="zip_recruiter">ZipRecruiter</option>
              <option value="glassdoor">Glassdoor</option>
              <option value="naukri">Naukri</option>
            </select>
          </label>
          <label>
            <span>Posted within</span>
            <div className="duration-control">
              <input
                name="postedWithin"
                type="number"
                value={postedWithin}
                onChange={(event) => setPostedWithin(Number(event.target.value))}
                min="1"
                max={timeUnit === "days" ? 30 : 720}
                step="1"
                inputMode="numeric"
                aria-label="Posted within value"
                required
              />
              <select
                name="timeUnit"
                value={timeUnit}
                onChange={(event) => {
                  const nextUnit = event.target.value as "hours" | "days";
                  setPostedWithin((current) =>
                    nextUnit === "hours" ? Math.min(current * 24, 720) : Math.max(1, Math.ceil(current / 24)),
                  );
                  setTimeUnit(nextUnit);
                }}
                aria-label="Posted within unit"
              >
                <option value="hours">Hours</option>
                <option value="days">Days</option>
              </select>
            </div>
          </label>
          <label>
            <span>Results per source</span>
            <select name="resultsWanted" defaultValue="5">
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="15">15</option>
              <option value="25">25</option>
            </select>
          </label>
          <label>
            <span>Work arrangement</span>
            <select name="workMode" defaultValue="all">
              <option value="all">All arrangements</option>
              <option value="remote">Remote only</option>
              <option value="onsite">Onsite only</option>
            </select>
          </label>
          <div className="toggles">
            <label><input type="checkbox" name="fetchDescriptions" /> Full descriptions</label>
          </div>
          <button type="submit" disabled={loading}>
            {loading ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
            {loading ? "Searching..." : "Search jobs"}
          </button>
        </form>

        <section className="results" aria-live="polite">
          <div className="results-header">
            <h2>Search results</h2>
            {summary && <span>{summary}</span>}
          </div>

          {error && <div className="message error">{error}</div>}
          {warning && <div className="message">{warning}</div>}
          {!error && !loading && !summary && <div className="message">Run a search to see matching jobs.</div>}
          {!error && !loading && summary && jobs.length === 0 && <div className="message">No jobs matched this search. Remote and onsite filters exclude hybrid listings and listings without a clear matching work arrangement.</div>}

          <div className="job-list">
            {jobs.map((job, index) => (
              <article className="job" key={job.id ?? `${job.jobUrl}-${index}`}>
                <div className="job-main">
                  <div className="job-title-row">
                    <h3>{job.title}</h3>
                    <span className="source">{job.site}</span>
                  </div>
                  <p className="company">{job.company ?? "Company not provided"}</p>
                  <div className="meta">
                    <span><MapPin size={15} /> {job.location ?? "Location not provided"}</span>
                    {job.datePosted && <span>Posted {new Date(job.datePosted).toLocaleDateString()}</span>}
                    {job.isRemote && <span>Remote</span>}
                    {job.jobType && <span>{job.jobType}</span>}
                  </div>
                  {job.description && <p className="description">{job.description.replace(/[#*_`]/g, "").slice(0, 280)}...</p>}
                </div>
                <div className="actions">
                  {job.directUrl && <a className="secondary" href={job.directUrl} target="_blank" rel="noreferrer">Company site <ExternalLink size={15} /></a>}
                  <a className="primary" href={job.jobUrl} target="_blank" rel="noreferrer">Open listing <ExternalLink size={15} /></a>
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
