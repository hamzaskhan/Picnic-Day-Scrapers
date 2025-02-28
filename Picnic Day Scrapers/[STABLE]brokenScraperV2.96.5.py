import os
import re
import csv
import requests
import html  # for unescaping HTML entities
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.setrecursionlimit(10000)

# Define the set of error status codes we care about. You can add more like 999, 401 etc.
ERROR_CODES = {404}

def is_valid(url):
    """
    Check if the URL is valid (has a scheme and network location).
    """
    parsed = urlparse(url)
    return bool(parsed.scheme) and bool(parsed.netloc)

def get_all_links(html_content, base_url):
    """
    Parse HTML and return a set of all URLs found.
    Scans every tag for common attributes (href, src, action, data-href, data-src)
    and uses a regex to search the entire HTML for URL-like strings.
    Before joining the URL, HTML entities (like &#x2B;) are unescaped.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    links = set()
    url_attrs = ["href", "src", "action", "data-href", "data-src"]
    for tag in soup.find_all(True):
        for attr in url_attrs:
            if tag.has_attr(attr):
                url_candidate = tag.get(attr)
                if url_candidate:
                    # Unescape HTML entities (e.g., &#x2B; becomes +)
                    url_candidate = html.unescape(url_candidate)
                    full_url = urljoin(base_url, url_candidate)
                    # Accept file:// URLs and any valid http(s) URL.
                    if full_url.startswith("file://") or is_valid(full_url):
                        links.add(full_url)
    regex_pattern = r'https?://[^\s"\'<>]+'
    for match in re.findall(regex_pattern, html_content):
        unescaped_match = html.unescape(match)
        full_url = urljoin(base_url, unescaped_match)
        if is_valid(full_url):
            links.add(full_url)
    return links

def scrape_page(url):
    """
    Retrieve the page content. For file:// URLs, reads the local file.
    For http(s) URLs, sends a GET request.
    Returns a dictionary with the page's URL, title, text, images, and links.
    """
    try:
        if url.startswith("file://"):
            path = url2pathname(urlparse(url).path)
            if not os.path.exists(path):
                print(f"Warning: Local file not found: {url}")
                return None
            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        else:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"Warning: Received status code {response.status_code} for URL: {url}")
                return None
            content = response.text

        soup = BeautifulSoup(content, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        text = soup.get_text(separator=" ", strip=True)
        images = []
        for img in soup.find_all("img", src=True):
            img_src = urljoin(url, img["src"])
            alt_text = img.get("alt", "").strip()
            images.append({"original_url": img_src, "alt_text": alt_text})
        links = get_all_links(content, url)
        return {"url": url, "title": title, "text": text, "images": images, "links": links}
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def check_link(url):
    """
    Check the URL using a HEAD request.
    Returns a tuple (status, error). Only if status is in our ERROR_CODES set
    will the caller consider the link broken.
    """
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        if response.status_code in ERROR_CODES:
            return response.status_code, f"Status {response.status_code}"
        return response.status_code, ""
    except Exception as e:
        return None, str(e)

def process_input_url(url):
    """
    Process a single input URL: scrape the page, extract all links,
    and check each link (and the main page itself) using HEAD requests concurrently.
    Only records with a status code in ERROR_CODES are returned.
    Each record is a dictionary with:
      - 'parent_url': The URL where the broken link was found.
      - 'broken_link': The broken URL.
      - 'status': The HTTP status code.
      - 'error': The error message.
      
    This function processes only the given URL (one level deep).
    """
    records = []
    print(f"\nProcessing: {url}")
    page_data = scrape_page(url)
    if not page_data:
        return records

    # Check the main page itself.
    status, error = check_link(url)
    if status is not None and status in ERROR_CODES:
        records.append({
            "parent_url": url,
            "broken_link": url,
            "status": status,
            "error": error or "Broken main page"
        })

    links = list(page_data["links"])
    print(f"Found {len(links)} links on {url}. Checking concurrently...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_link = {executor.submit(check_link, link): link for link in links}
        for future in as_completed(future_to_link):
            link = future_to_link[future]
            try:
                status, error = future.result()
            except Exception as exc:
                status, error = None, str(exc)
            if status is not None and status in ERROR_CODES:
                records.append({
                    "parent_url": url,
                    "broken_link": link,
                    "status": status,
                    "error": error
                })
    return records

if __name__ == "__main__":
    input_filename = input("Enter input filename (CSV or TXT; each row/line should contain one URL): ").strip()
    if not input_filename:
        print("No input file provided. Exiting.")
        sys.exit(1)

    output_csv = "broken_links_output.csv"
    all_records = []
    urls = []

    # Determine file type by extension (case-insensitive)
    ext = os.path.splitext(input_filename)[1].lower()
    if ext == ".txt":
        with open(input_filename, "r", encoding="utf-8-sig") as f:
            for line in f:
                url = line.strip()
                if url:
                    urls.append(url)
    else:
        import csv
        with open(input_filename, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if row:
                    url = row[0].strip()
                    if url:
                        urls.append(url)

    print(f"Processing {len(urls)} URLs concurrently...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(process_input_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            records = future.result()
            all_records.extend(records)

    # Write complete output CSV (only records with error status in ERROR_CODES).
    with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["parent_url", "broken_link", "status", "error"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_records:
            writer.writerow(rec)

    print(f"\nBroken link report written to {output_csv}.")
