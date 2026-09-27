import csv
import json
import math

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render

from .forms import SearchForm
from .naukri_client import search_jobs, normalize_job

JOBS_PER_PAGE = getattr(settings, "JOBS_PER_PAGE", 15)


def index(request):
    """
    Home / search-results view.
    GET ?keyword=python&page=2  → run search, show results
    GET (no keyword)            → show empty search form
    """
    form = SearchForm(request.GET or None)
    jobs = []
    total_jobs = 0
    total_pages = 0
    current_page = 1
    error = None
    keyword = ""

    if form.is_valid():
        keyword = form.cleaned_data["keyword"].strip()
        current_page = max(1, int(request.GET.get("page", 1)))

        result = search_jobs(keyword, page=current_page)
        error = result["error"]

        if not error:
            jobs = [normalize_job(j) for j in result["jobs"]]
            total_jobs = result["noOfJobs"]
            total_pages = math.ceil(total_jobs / JOBS_PER_PAGE)

    page_range = _get_page_range(current_page, total_pages)

    context = {
        "form": form,
        "jobs": jobs,
        "keyword": keyword,
        "total_jobs": total_jobs,
        "current_page": current_page,
        "total_pages": total_pages,
        "page_range": page_range,
        "error": error,
        "searched": form.is_valid(),
    }
    return render(request, "naukri/index.html", context)


def job_detail(request, job_id):
    """
    Job-detail view.

    The JS passes an already-normalized job dict via ?data=<json>.
    We use it directly — no second normalize_job() call needed.
    Fallback: re-fetch from API if data param is missing.
    """
    raw_data = request.GET.get("data")
    keyword  = request.GET.get("keyword", "")
    page     = request.GET.get("page", "1")

    job = None

    if raw_data:
        try:
            # Data is already a normalized dict — use as-is
            job = json.loads(raw_data)
        except (json.JSONDecodeError, Exception):
            job = None

    # Fallback: re-fetch from API and normalize
    if not job and keyword:
        try:
            result = search_jobs(keyword, page=int(page))
            for raw in result.get("jobs", []):
                if str(raw.get("jobId", "")) == str(job_id):
                    job = normalize_job(raw)
                    break
        except Exception:
            pass

    if not job:
        raise Http404("Job not found. Please go back and search again.")

    context = {
        "job": job,
        "keyword": keyword,
        "page": page,
    }
    return render(request, "naukri/job_detail.html", context)


def export_csv(request):
    """
    Export current search results as a CSV file.
    GET ?keyword=python&page=1
    Fetches the same page and streams it as a CSV download.
    """
    keyword      = request.GET.get("keyword", "").strip()
    current_page = max(1, int(request.GET.get("page", 1)))

    if not keyword:
        return HttpResponse("No keyword provided.", status=400)

    result = search_jobs(keyword, page=current_page)
    if result["error"]:
        return HttpResponse(f"Error: {result['error']}", status=500)

    jobs = [normalize_job(j) for j in result["jobs"]]

    # Build HTTP response with CSV content
    response = HttpResponse(content_type="text/csv")
    filename = f"naukri_{keyword.replace(' ', '_')}_p{current_page}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    # Header row
    writer.writerow([
        "Job Title", "Company", "Experience", "Salary",
        "Location", "Skills", "Vacancies", "Posted",
        "Min Experience (Yrs)", "Max Experience (Yrs)",
        "Salary Hidden", "Min Salary", "Max Salary",
        "Today's Job", "Walk-in", "Apply By", "Listed On",
        "AB Rating", "AB Reviews",
        "Job ID", "Apply URL",
    ])
    # Data rows
    for j in jobs:
        writer.writerow([
            j.get("title", ""),
            j.get("company_name", ""),
            j.get("experience", ""),
            j.get("salary_display", ""),
            j.get("location", ""),
            ", ".join(j.get("tags", [])),
            j.get("vacancy", ""),
            j.get("posted_label", ""),
            j.get("min_exp", ""),
            j.get("max_exp", ""),
            "Yes" if j.get("salary_hidden") else "No",
            j.get("min_salary", ""),
            j.get("max_salary", ""),
            "Yes" if j.get("today") else "No",
            "Yes" if j.get("walkin") else "No",
            j.get("apply_by", ""),
            j.get("created_date", ""),
            j.get("ab_rating", ""),
            j.get("ab_reviews", ""),
            j.get("job_id", ""),
            j.get("naukri_apply_url", ""),
        ])

    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_page_range(current: int, total: int, window: int = 3) -> list:
    """Return a list of page numbers (with None as ellipsis markers)."""
    if total <= 1:
        return []
    visible = {1, total}
    for p in range(max(1, current - window), min(total, current + window) + 1):
        visible.add(p)
    pages = []
    prev = None
    for p in sorted(visible):
        if prev is not None and p - prev > 1:
            pages.append(None)
        pages.append(p)
        prev = p
    return pages
