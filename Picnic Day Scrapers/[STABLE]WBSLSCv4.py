import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname
import sys
import json
import csv

sys.setrecursionlimit(10000)

def is_valid(url):
    """
    Check if the URL is valid (has a scheme and network location).
    """
    parsed = urlparse(url)
    return bool(parsed.scheme) and bool(parsed.netloc)

def get_all_links(html_content, base_url):
    """
    Parse HTML and return a set of internal links.
    
    This function scans common attributes (including oneclick), meta refresh tags,
    inline CSS references, and uses regex to capture any URL-like strings.
    
    Only URLs that either start with file:// or belong to the same domain as base_url are returned.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    links = set()
    # Attributes to search for potential URLs.
    url_attrs = ["href", "src", "action", "data-href", "data-src", "data-url", "data-link", "oneclick"]
    for tag in soup.find_all(True):
        for attr in url_attrs:
            if tag.has_attr(attr):
                url_candidate = tag.get(attr)
                if url_candidate:
                    full_url = urljoin(base_url, url_candidate)
                    if full_url.startswith("file://"):
                        links.add(full_url)
                    elif is_valid(full_url) and urlparse(full_url).netloc == urlparse(base_url).netloc:
                        links.add(full_url)
    
    # Capture meta refresh tags (e.g., <meta http-equiv="refresh" content="5;url=http://example.com/">)
    for meta in soup.find_all("meta", attrs={"http-equiv": lambda x: x and x.lower() == "refresh"}):
        content = meta.get("content", "")
        match = re.search(r'url=([\S]+)', content, re.IGNORECASE)
        if match:
            url_candidate = match.group(1).strip().strip('\'"')
            full_url = urljoin(base_url, url_candidate)
            if full_url.startswith("file://"):
                links.add(full_url)
            elif is_valid(full_url) and urlparse(full_url).netloc == urlparse(base_url).netloc:
                links.add(full_url)
    
    # Capture URLs inside inline CSS (e.g., background-image: url(...))
    css_urls = re.findall(r'url\(([^)]+)\)', html_content)
    for css_url in css_urls:
        css_url = css_url.strip().strip('\'"')
        full_url = urljoin(base_url, css_url)
        if full_url.startswith("file://"):
            links.add(full_url)
        elif is_valid(full_url) and urlparse(full_url).netloc == urlparse(base_url).netloc:
            links.add(full_url)
    
    # Additionally, use regex to catch any URLs in the raw HTML.
    regex_pattern = r'https?://[^\s"\'<>]+'
    for match in re.findall(regex_pattern, html_content):
        full_url = urljoin(base_url, match)
        if full_url.startswith("file://"):
            links.add(full_url)
        elif is_valid(full_url) and urlparse(full_url).netloc == urlparse(base_url).netloc:
            links.add(full_url)
    return links

def scrape_page(url):
    """
    Scrape a page:
      - For HTTP(s) URLs, fetch via requests.
      - For file URLs, read the local file.
    Returns a dict with URL, title, text, images, and links.
    """
    try:
        if url.startswith("file://"):
            # Convert file:// URL to a local file path.
            path = url2pathname(urlparse(url).path)
            if not os.path.exists(path):
                print(f"Warning: Local file not found: {url}")
                return None
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"Warning: Received status code {response.status_code} for URL: {url}")
                return None
            # Ensure response text is decoded in UTF-8.
            response.encoding = "utf-8"
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

def build_tree(url, base_domain, max_depth, visited):
    """
    Recursively scrape pages to build a tree structure of links.
    Each node contains the URL, title, list of directly found links, and children nodes.
    """
    if url in visited:
        return None

    print(f"Scraping: {url}")
    visited.add(url)
    page_data = scrape_page(url)
    if not page_data:
        return None

    node = {
        "url": page_data["url"],
        "title": page_data["title"],
        "links": sorted(page_data["links"]),
        "children": []
    }
    if max_depth > 0:
        for link in page_data["links"]:
            # For file URLs, follow only file URLs.
            if url.startswith("file://"):
                if link.startswith("file://"):
                    child = build_tree(link, base_domain, max_depth - 1, visited)
                    if child:
                        node["children"].append(child)
            else:
                if urlparse(link).netloc == base_domain:
                    child = build_tree(link, base_domain, max_depth - 1, visited)
                    if child:
                        node["children"].append(child)
    return node

def traverse_tree(node, unique_links=None):
    """
    Recursively traverse the tree to collect unique URLs with their titles.
    Returns a dictionary with URLs as keys and titles as values.
    """
    if unique_links is None:
        unique_links = {}

    url = node.get("url")
    if url and url not in unique_links:
        unique_links[url] = node.get("title", "")
    
    for child in node.get("children", []):
        traverse_tree(child, unique_links)
    
    return unique_links

if __name__ == "__main__":
    website_url = input("Enter the website URL to crawl [default: https://hamzak.cloud]: ").strip()
    if not website_url:
        website_url = "https://hamzak.cloud"
    max_depth_input = input("Enter the maximum depth to crawl [default: 1]: ").strip()
    try:
        max_depth = int(max_depth_input) if max_depth_input else 1
    except ValueError:
        max_depth = 1

    parsed_base = urlparse(website_url)
    if parsed_base.scheme == "file":
        base_domain = website_url
    else:
        base_domain = parsed_base.netloc

    visited = set()
    tree = build_tree(website_url, base_domain, max_depth, visited)
    
    # Save the link tree in an organized JSON format.
    output_json = "link_tree.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
    
    print(f"\nLink tree has been saved to {output_json}")

    # Traverse the tree to collect unique URLs.
    unique_links = traverse_tree(tree)
    
    # Write the unique links to a CSV file.
    output_csv = "unique_links.csv"
    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["URL", "Title"])
        for url, title in unique_links.items():
            writer.writerow([url, title])
    
    print(f"Unique links have been saved to {output_csv}")
