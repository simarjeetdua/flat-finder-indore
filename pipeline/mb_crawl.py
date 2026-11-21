
"""Polite, cached, resumable Magicbricks crawler.

Usage:
    python pipeline/mb_crawl.py list indore
    python pipeline/mb_crawl.py projects indore
"""

import gzip
import hashlib
import json
import pathlib
import sys
import time
import urllib.request
import urllib.error

import mb_parse


# --------------------------------------------------
# PROJECT CONFIGURATION
# --------------------------------------------------

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "mb"
BASE_OUT = ROOT / "out"

CITIES = json.loads(
    (ROOT.parent / "data" / "cities.json").read_text(encoding="utf-8")
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

DELAY = 1.5
MAX_RETRIES = 3
MAX_PAGES = 100


# These are configured by main()
CITY = None
CFG = None
LIST_URL = None
OUT = None


# --------------------------------------------------
# RESPONSE VALIDATION
# --------------------------------------------------

def valid_html(html, expected="list"):
    """Check whether the response resembles the expected page."""

    if not html or len(html) < 2000:
        return False

    if expected == "list":
        return (
            '"psmName":' in html
            or '"totalCount":' in html
        )

    if expected == "detail":
        return (
            "SERVER_PRELOADED_STATE_" in html
            or "projectDetailData" in html
        )

    return True


# --------------------------------------------------
# FETCH WITH CACHE AND RETRIES
# --------------------------------------------------

def fetch(url, expected="list"):

    CACHE.mkdir(parents=True, exist_ok=True)

    filename = hashlib.sha1(
        url.encode("utf-8")
    ).hexdigest() + ".html.gz"

    cache_file = CACHE / filename

    # Check existing cache
    if cache_file.exists():

        try:
            cached = gzip.decompress(
                cache_file.read_bytes()
            ).decode("utf-8", "ignore")

            if valid_html(cached, expected):
                print("  CACHE:", url, flush=True)
                return cached

            print("  Invalid cached HTML. Removing cache.", flush=True)
            cache_file.unlink()

        except Exception:
            cache_file.unlink(missing_ok=True)

    # Fetch fresh HTML
    for attempt in range(1, MAX_RETRIES + 1):

        try:

            headers = {
                "User-Agent": UA,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,image/avif,"
                    "image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }

            req = urllib.request.Request(
                url,
                headers=headers
            )

            with urllib.request.urlopen(
                req,
                timeout=40
            ) as response:

                status = response.status

                html = response.read().decode(
                    "utf-8", "ignore"
                )

            print(
                f"  HTTP {status} | HTML size: {len(html)}",
                flush=True
            )

            if not valid_html(html, expected):

                print(
                    "  ERROR: Response does not contain "
                    "expected Magicbricks data.",
                    flush=True
                )

                print(
                    "  URL:", url,
                    flush=True
                )

                print(
                    "  Response preview:",
                    html[:300].replace("\n", " "),
                    flush=True
                )

                # Do not cache placeholder or blocked HTML.
                return None

            # Save only validated HTML
            cache_file.write_bytes(
                gzip.compress(
                    html.encode("utf-8"),
                    compresslevel=9
                )
            )

            time.sleep(DELAY)

            return html

        except urllib.error.HTTPError as e:

            print(
                f"  HTTP ERROR {e.code}: {url}",
                flush=True
            )

            # Do not repeatedly retry access restrictions.
            if e.code in (401, 403, 404, 429):
                return None

            if attempt == MAX_RETRIES:
                return None

        except Exception as e:

            print(
                f"  RETRY {attempt}/{MAX_RETRIES}: {e}",
                flush=True
            )

            if attempt == MAX_RETRIES:
                return None

        time.sleep(3 * attempt)

    return None


# --------------------------------------------------
# LIST CRAWLER
# --------------------------------------------------

def crawl_list():

    print("\nStarting Magicbricks list crawler")
    print("City:", CITY)
    print("URL:", LIST_URL.format(1))
    print("-" * 55)

    first = fetch(
        LIST_URL.format(1),
        expected="list"
    )

    if not first:
        print("\nFAILED: Could not retrieve valid listing HTML.")
        return

    total = mb_parse.parse_total(first)

    # Parse first page even when totalCount is missing.
    first_cards = mb_parse.parse_list_page(first)

    if not first_cards:
        print("\nFAILED: No project cards found on page 1.")
        print("Check Magicbricks response and mb_parse.py.")
        return

    projects = {}

    def add_cards(cards):

        for card in cards:

            psmid = card.get("psmid")
            pdp_url = card.get("pdpUrl")

            if not psmid or not pdp_url:
                continue

            projects[psmid] = mb_parse.card_to_project(card)

    add_cards(first_cards)

    print(
        f"Page 1: {len(projects)} projects found",
        flush=True
    )

    # Use totalCount when available.
    if total is not None:

        pages = min(
            (total + 19) // 20,
            MAX_PAGES
        )

        print("Reported projects:", total)
        print("Pages to crawl:", pages)

        for n in range(2, pages + 1):

            html = fetch(
                LIST_URL.format(n),
                expected="list"
            )

            if not html:
                print(f"Skipping page {n}")
                continue

            cards = mb_parse.parse_list_page(html)

            if not cards:
                print(f"No cards on page {n}. Stopping.")
                break

            add_cards(cards)

            print(
                f"Page {n}/{pages}: "
                f"{len(projects)} total projects",
                flush=True
            )

    else:

        # If totalCount is missing, use pagination
        # until the website returns an empty page.
        print(
            "WARNING: totalCount unavailable. "
            "Using fallback pagination."
        )

        for n in range(2, MAX_PAGES + 1):

            html = fetch(
                LIST_URL.format(n),
                expected="list"
            )

            if not html:
                print("Pagination stopped: invalid response.")
                break

            cards = mb_parse.parse_list_page(html)

            if not cards:
                print("No more project cards.")
                break

            old_count = len(projects)
            add_cards(cards)

            print(
                f"Page {n}: {len(projects)} total projects",
                flush=True
            )

            if len(projects) == old_count:
                print("No new projects found. Stopping.")
                break

    # Save results
    OUT.mkdir(parents=True, exist_ok=True)

    output_file = OUT / "mb_index.json"

    output_file.write_text(
        json.dumps(
            list(projects.values()),
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\n" + "=" * 45)
    print("MAGICBRICKS CRAWL COMPLETE")
    print("City:", CITY)
    print("Reported:", total)
    print("Collected:", len(projects))
    print("Output:", output_file)
    print("=" * 45)


# --------------------------------------------------
# PROJECT DETAIL CRAWLER
# --------------------------------------------------

def crawl_projects():

    index_file = OUT / "mb_index.json"

    if not index_file.exists():
        print("ERROR: mb_index.json not found.")
        print("Run the list crawler first.")
        return

    index = json.loads(
        index_file.read_text(encoding="utf-8")
    )

    if not index:
        print("ERROR: No projects available to crawl.")
        return

    print("\nStarting project detail crawler")
    print("Projects:", len(index))

    from concurrent.futures import ThreadPoolExecutor

    def one(project):

        url = project.get("url")

        if not url:
            return project

        html = fetch(
            url,
            expected="detail"
        )

        if not html:
            print("  Detail page unavailable:", url)
            return project

        try:

            detail = mb_parse.parse_project_page(html)

            return {
                **project,
                **{
                    k: v
                    for k, v in detail.items()
                    if v not in (None, [], "")
                }
            }

        except Exception as e:

            print(
                "  Parse failed:",
                url,
                e,
                flush=True
            )

            return project

    output_file = OUT / "mb_projects.json"

    results = []

    with ThreadPoolExecutor(max_workers=3) as executor:

        for i, result in enumerate(
            executor.map(one, index),
            start=1
        ):

            results.append(result)

            if i % 25 == 0 or i == len(index):

                output_file.write_text(
                    json.dumps(
                        results,
                        indent=2,
                        ensure_ascii=False
                    ),
                    encoding="utf-8"
                )

                print(
                    f"Processed {i}/{len(index)} projects",
                    flush=True
                )

    print("\nProject crawling complete.")
    print("Total processed:", len(results))
    print("Output:", output_file)


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    global CITY, CFG, LIST_URL, OUT

    if len(sys.argv) < 2:

        print("Usage:")
        print("  python pipeline/mb_crawl.py list indore")
        print("  python pipeline/mb_crawl.py projects indore")
        return

    mode = sys.argv[1].lower()

    if mode not in ("list", "projects"):

        print("ERROR: Invalid command:", mode)
        print("Available commands: list, projects")
        return

    CITY = sys.argv[2].lower() if len(sys.argv) > 2 else "gurgaon"

    if CITY not in CITIES:

        print("ERROR: Unknown city:", CITY)
        print("Available cities:", ", ".join(CITIES.keys()))
        return

    CFG = CITIES[CITY]

    LIST_URL = CFG.get("list_url") or (
        "https://www.magicbricks.com/residential-projects-in-"
        + CFG["magicbricks"]
        + "-nprid/page-{}"
    )

    if "{}" not in LIST_URL:

        print("ERROR: list_url must contain a {} page placeholder.")
        print("Current URL:", LIST_URL)
        return

    OUT = BASE_OUT / CITY

    if mode == "list":
        crawl_list()

    elif mode == "projects":
        crawl_projects()


if __name__ == "__main__":
    main()
