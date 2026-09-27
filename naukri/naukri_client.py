"""
Naukri API client using real Chrome (via Playwright) to capture fresh headers.

Confirmed working approach (test_intercept.py output):
  - channel="chrome" passes bot detection; bundled Chromium does not.
  - Captured headers include: accept-language, content-type, cookie, referer,
    user-agent, accept, appid, clientid, gid, nkparam, sec-ch-ua*, systemid.
  - nkparam rotates every session — browser generates it fresh each time.
"""

import datetime
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def _fetch_live_headers(keyword: str) -> dict:
    """
    Launch real Chrome, navigate to Naukri SRP for *keyword*, intercept the
    jobapi/v3/search XHR, and return the full header dict from that request.
    """
    captured: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            extra_http_headers={
                "accept-language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        page = context.new_page()

        def handle_route(route):
            # Capture on first jobapi hit only
            if not captured:
                captured.update(route.request.headers)
                print(f"[naukri] intercepted — nkparam={captured.get('nkparam','?')!r}")
            route.continue_()

        # Register BEFORE navigation so we catch the very first XHR
        page.route("**/jobapi/v3/search**", handle_route)

        seo_key = keyword.strip().replace(" ", "-").lower() + "-jobs"
        nav_url = (
            f"https://www.naukri.com/{seo_key}"
            f"?k={keyword}&nignbevent_src=jobsearchDeskGNB&jobAge=1"
        )
        print(f"[naukri] navigating: {nav_url}")

        try:
            page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            print("[naukri] goto timeout (ok if headers captured)")
        except Exception as exc:
            print(f"[naukri] goto error: {exc}")

        # Wait a bit more if the XHR hasn't fired yet
        if not captured:
            print("[naukri] waiting 6s for XHR...")
            try:
                page.wait_for_timeout(6000)
            except Exception:
                pass

        browser.close()

    return captured


def _build_url(keyword: str, page: int) -> str:
    """Exact URL format from the working HAR. jobAge=1 appears twice."""
    seo_key = keyword.strip().replace(" ", "-").lower() + "-jobs"
    return (
        "https://www.naukri.com/jobapi/v3/search"
        f"?noOfResults=20"
        f"&urlType=search_by_keyword"
        f"&searchType=adv"
        f"&keyword={keyword}"
        f"&pageNo={page}"
        f"&jobAge=1"
        f"&k={keyword}"
        f"&nignbevent_src=jobsearchDeskGNB"
        f"&jobAge=1"
        f"&seoKey={seo_key}"
        f"&src=jobsearchDesk"
        f"&latLong="
    )


def search_jobs(keyword: str, page: int = 1) -> dict:
    """
    Search Naukri for jobs matching *keyword* on the given *page*.

    Returns:
        noOfJobs  – total count (int)
        jobs      – list of raw jobDetails dicts
        error     – error message string, or None
    """
    if not keyword:
        return {"noOfJobs": 0, "jobs": [], "error": None}

    kw = keyword.strip()

    # Step 1 — get fresh headers from a real Chrome session
    print(f"[naukri] capturing headers for '{kw}'...")
    live_headers = _fetch_live_headers(kw)

    if not live_headers:
        return {
            "noOfJobs": 0,
            "jobs": [],
            "error": "Could not capture API headers from browser. Please try again.",
        }

    # Step 2 — use those headers to fetch the desired page
    url = _build_url(kw, page)
    print(f"[naukri] fetching page {page}: {url}")

    try:
        response = requests.get(url, headers=live_headers, timeout=15)
        print(f"[naukri] status={response.status_code} len={len(response.text)}")
        response.raise_for_status()
        data = response.json()

        return {
            "noOfJobs": data.get("noOfJobs", 0),
            "jobs": data.get("jobDetails", []),
            "error": None,
        }

    except requests.exceptions.Timeout:
        return {"noOfJobs": 0, "jobs": [], "error": "Request timed out. Please try again."}

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        body = exc.response.text[:300] if exc.response is not None else ""
        print(f"[naukri] HTTPError {status}: {body!r}")
        return {
            "noOfJobs": 0,
            "jobs": [],
            "error": f"API error {status}. Please try again.",
        }

    except ValueError as exc:
        print(f"[naukri] JSON error: {exc} | body: {response.text[:300]!r}")
        return {
            "noOfJobs": 0,
            "jobs": [],
            "error": "Unexpected response from Naukri. Check server console.",
        }

    except Exception as exc:  # noqa: BLE001
        print(f"[naukri] Unexpected: {exc}")
        return {"noOfJobs": 0, "jobs": [], "error": f"Unexpected error: {exc}"}


def normalize_job(raw: dict) -> dict:
    """Flatten a raw jobDetails entry into a clean dict for templates."""
    placeholders = {p["type"]: p["label"] for p in raw.get("placeholders", [])}
    salary_detail = raw.get("salaryDetail", {})

    if salary_detail.get("hideSalary"):
        salary_display = "Not disclosed"
    elif salary_detail.get("minimumSalary") and salary_detail.get("maximumSalary"):
        min_lac = salary_detail["minimumSalary"] / 100000
        max_lac = salary_detail["maximumSalary"] / 100000
        salary_display = f"₹{min_lac:.1f}L – ₹{max_lac:.1f}L PA"
    else:
        salary_display = placeholders.get("salary", "Not disclosed")

    ab = raw.get("ambitionBoxData", {})
    tags = [t.strip() for t in raw.get("tagsAndSkills", "").split(",") if t.strip()]

    created_ms = raw.get("createdDate")
    created_date = None
    if created_ms:
        created_date = datetime.datetime.fromtimestamp(
            created_ms / 1000
        ).strftime("%d %b %Y")

    return {
        "job_id": raw.get("jobId", ""),
        "jd_url": raw.get("jdURL", ""),
        "company_name": raw.get("companyName", ""),
        "company_logo": raw.get("logoPathV3") or raw.get("logoPath", ""),
        "company_id": raw.get("companyId"),
        "static_url": raw.get("staticUrl", ""),
        "hiring_for": raw.get("hiringFor", ""),
        "is_consultant": raw.get("consultant", False),
        "title": raw.get("title", ""),
        "experience": placeholders.get("experience", ""),
        "location": placeholders.get("location", ""),
        "salary_display": salary_display,
        "min_salary": salary_detail.get("minimumSalary", 0),
        "max_salary": salary_detail.get("maximumSalary", 0),
        "salary_hidden": salary_detail.get("hideSalary", True),
        "min_exp": raw.get("minimumExperience", ""),
        "max_exp": raw.get("maximumExperience", ""),
        "experience_text": raw.get("experienceText", ""),
        "job_description": raw.get("jobDescription", ""),
        "tags": tags,
        "vacancy": raw.get("vacancy"),
        "posted_label": raw.get("footerPlaceholderLabel", ""),
        "posted_color": raw.get("footerPlaceholderColor", "green"),
        "created_date": created_date,
        "today": raw.get("todaysJob", False),
        "walkin": raw.get("walkinJob", False),
        "apply_by": raw.get("applyByTime", ""),
        "mode": raw.get("mode", ""),
        "board": raw.get("board", ""),
        "ab_rating": ab.get("AggregateRating"),
        "ab_reviews": ab.get("ReviewsCount"),
        "ab_url": ab.get("Url", ""),
        "ab_title": ab.get("Title", ""),
        "show_multiple_apply": raw.get("showMultipleApply", False),
        "company_apply": raw.get("companyApplyJob", False),
        "naukri_apply_url": f"https://www.naukri.com{raw.get('jdURL', '')}",
    }
