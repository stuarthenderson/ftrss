#!/usr/bin/env python3
"""
generate_rss_feed.py
====================

This script reads one or more RSS feeds (for example, the Financial Times
podcasts hosted on Acast) and extracts the "free to read" and "mentioned in
this podcast" links from each episode.  It then produces a new RSS 2.0 feed
containing one item for each extracted article link.  Each generated item
includes the article title (or URL if no title is available), the original
link and a short description referencing the source podcast episode.

Usage
-----

Run the script from the root of your repository.  By default it will read
from the two FT podcast feeds used in the example problem:

    https://feeds.acast.com/public/shows/ft-tech-tonic
    https://feeds.acast.com/public/shows/ftnewsbriefing

You can override the list of feeds by setting the ``FEED_URLS`` environment
variable to a space‑delimited list of URLs.  The generated feed will be
written to ``output/generated_feed.xml`` relative to the repository root.

The script requires the ``feedparser`` and ``beautifulsoup4`` libraries.  See
the accompanying GitHub Action workflow for an example of how to install
these dependencies automatically.

Background
----------

Financial Times (FT) podcast episodes often contain lists of articles that
listeners can read for free or articles that are mentioned during the show.
Within the RSS description field these lists are prefaced by bold text such
as "Free to read:" or "Mentioned in this podcast:".  Immediately
following these headings are one or more anchor (<a>) tags pointing to
the relevant articles.  In the Tech Tonic feed, for example, the first
episode in July 2025 contains a "Free to read" section with four FT
articles after the summary【641746954568272†L20-L30】.  In older episodes the
phrase "Mentioned in this podcast" appears instead【641746954568272†L1220-L1225】.  This
script scans the description for these markers, collects all links that
appear immediately after them until the next bold heading, and excludes
irrelevant links such as email addresses or sign‑up prompts.
"""

from __future__ import annotations

import os
import sys
import time
import email.utils
from typing import Iterable, List, Dict, Tuple, Optional, Any

try:
    import feedparser  # type: ignore
except ImportError:
    sys.stderr.write(
        "The 'feedparser' library is required. Install it with 'pip install feedparser'.\n"
    )
    raise

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    sys.stderr.write(
        "The 'beautifulsoup4' library is required. Install it with 'pip install beautifulsoup4'.\n"
    )
    raise


def extract_article_links(description_html: str) -> List[Tuple[str, str]]:
    """Extract article links from an episode description.

    Looks for bold headings that contain the keywords "free to read" or
    "mentioned in this podcast" and returns all anchor tags that
    immediately follow such headings.  Links that are not FT articles
    (e.g. mailto links or sign‑up forms) are filtered out.

    Parameters
    ----------
    description_html:
        The HTML content of the <description> element from the RSS entry.

    Returns
    -------
    list of (title, url):
        A list of article titles (or URL if the title is empty) and
        corresponding URLs.
    """
    soup = BeautifulSoup(description_html or "", "html.parser")
    article_links: List[Tuple[str, str]] = []

    # Keywords to look for in bold headings (case‑insensitive).
    markers = ["free to read", "mentioned in this podcast"]

    # Iterate over all <strong> tags to find markers.
    for strong_tag in soup.find_all("strong"):
        text = strong_tag.get_text(strip=True).lower()
        if any(marker in text for marker in markers):
            # Traverse subsequent elements until the next <strong> or <hr>
            for elem in strong_tag.next_elements:
                # Skip non‑tag elements (strings, comments, etc.)
                if not hasattr(elem, "name"):
                    continue
                # Stop when another marker or divider is encountered
                if elem.name in {"strong", "hr"}:
                    break
                # Collect <a> tags
                if elem.name == "a":
                    href = elem.get("href")
                    title_text = elem.get_text(strip=True)
                    # Skip if the anchor contains a nested <strong> (e.g. transcript links)
                    if elem.find("strong"):
                        continue
                    if not href:
                        continue
                    # Basic filtering: ignore mailto and obvious newsletter/survey links
                    href_lower = href.lower()
                    if href_lower.startswith("mailto:"):
                        continue
                    # Exclude certain FT subdomains that typically contain sign‑up pages
                    exclude_substrings = [
                        "ft.com/techtonicsurvey",
                        "ft.com/survey",
                        "ep.ft.com",
                        "subscribe",
                        "newsletters",
                        "newsletter",
                        "ft.com/support",
                    ]
                    if any(sub in href_lower for sub in exclude_substrings):
                        continue
                    # Only accept links that live on the Financial Times domains (ft.com or on.ft.com)
                    # Many podcast descriptions also contain Twitter spaces or other external content, which
                    # we exclude by default.  Parse out the domain and check it.
                    try:
                        from urllib.parse import urlparse  # imported lazily to avoid overhead
                        domain = urlparse(href).hostname or ""
                    except Exception:
                        domain = ""
                    if not (domain.endswith("ft.com") or domain.endswith("on.ft.com")):
                        continue
                    # If the link text looks like an email address or sign‑up prompt, ignore it
                    text_lower = title_text.lower()
                    if any(kw in text_lower for kw in [
                        "sign up", "subscribe", "transcript", "survey", "newsletter", "twitter"]):
                        continue
                    # If the anchor text is empty, fall back to the URL
                    if not title_text:
                        title_text = href
                    article_links.append((title_text, href))
            # Only process the first matching marker per description
            if article_links:
                break
    return article_links


def build_rss_channel(items: List[Dict[str, str]]) -> str:
    """Build a simple RSS 2.0 feed from a list of items.

    Parameters
    ----------
    items:
        A list of dictionaries containing keys: 'title', 'link', 'pubDate', and
        'description'.  The 'guid' field will be derived from the link.

    Returns
    -------
    str
        The XML content of the RSS feed as a string.
    """
    import xml.etree.ElementTree as ET

    rss = ET.Element("rss", attrib={"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    # Basic metadata for the generated feed
    ET.SubElement(channel, "title").text = "FT Podcast Articles Feed"
    ET.SubElement(channel, "link").text = "https://example.com/generated_feed.xml"
    ET.SubElement(channel, "description").text = (
        "An automatically generated feed of articles mentioned in FT "
        "podcasts. Each item corresponds to a free‑to‑read or mentioned "
        "article extracted from the podcast RSS feeds."
    )
    ET.SubElement(channel, "lastBuildDate").text = (
        email.utils.formatdate(time.time(), usegmt=True)
    )

    for item in items:
        itm = ET.SubElement(channel, "item")
        ET.SubElement(itm, "title").text = item["title"]
        ET.SubElement(itm, "link").text = item["link"]
        guid = ET.SubElement(itm, "guid", attrib={"isPermaLink": "true"})
        guid.text = item["link"]
        ET.SubElement(itm, "pubDate").text = item["pubDate"]
        ET.SubElement(itm, "description").text = item["description"]

    # Generate a pretty‑printed XML string
    xml_bytes = ET.tostring(rss, encoding="utf-8")
    # Add XML declaration
    xml_string = b"<?xml version='1.0' encoding='UTF-8'?>\n" + xml_bytes
    return xml_string.decode("utf-8")


def generate_html_pages(
    episodes: List[Dict[str, Any]], output_dir: str, per_page: int = 10
) -> None:
    """Generate paginated HTML files listing extracted links.

    Parameters
    ----------
    episodes:
        List of episode dictionaries containing keys ``podcast``,
        ``episode``, ``pubDate`` and ``links`` (a list of ``title`` and
        ``url`` pairs).
    output_dir:
        Directory where the HTML files will be written.
    per_page:
        Number of podcast entries per HTML page.
    """
    import html

    total_pages = (len(episodes) + per_page - 1) // per_page
    for page_num in range(total_pages):
        start = page_num * per_page
        page_eps = episodes[start : start + per_page]
        parts = [
            "<html><head><meta charset='utf-8'><title>FT Podcast Links - Page {}".format(
                page_num + 1
            ),
            "</title></head><body>",
        ]
        for ep in page_eps:
            date = html.escape(ep["pubDate"])
            podcast = html.escape(ep["podcast"])
            episode_title = html.escape(ep["episode"])
            parts.append(f"<h2>{date} - {podcast}: {episode_title}</h2>")
            parts.append("<ul>")
            for link in ep["links"]:
                title = html.escape(link["title"])
                url = html.escape(link["url"])
                parts.append(f"<li><a href='{url}'>{title}</a></li>")
            parts.append("</ul>")

        nav: List[str] = []
        if page_num > 0:
            nav.append(
                f"<a href='links_page_{page_num}.html'>Previous</a>"
            )
        if page_num < total_pages - 1:
            nav.append(
                f"<a href='links_page_{page_num + 2}.html'>Next</a>"
            )
        if nav:
            parts.append("<p>" + " | ".join(nav) + "</p>")
        parts.append("</body></html>")

        html_path = os.path.join(output_dir, f"links_page_{page_num + 1}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
    print(f"Generated {total_pages} HTML page(s) in {output_dir}")


def main() -> int:
    # Determine feed URLs either from the environment or default to FT podcast feeds
    default_feeds = [
        "https://feeds.acast.com/public/shows/ft-tech-tonic",
        "https://feeds.acast.com/public/shows/ftnewsbriefing",
    ]
    feed_urls_env = os.environ.get("FEED_URLS")
    if feed_urls_env:
        feed_urls = [url.strip() for url in feed_urls_env.split() if url.strip()]
    else:
        feed_urls = default_feeds

    all_items: List[Dict[str, str]] = []
    episodes: List[Dict[str, Any]] = []
    # Determine age limit (in days) for included episodes.  By default we
    # include only episodes from the last 5 days.  You can override this
    # behaviour by setting the DAYS_LIMIT environment variable to a
    # positive integer.
    try:
        days_limit = int(os.environ.get("DAYS_LIMIT", "5"))
        if days_limit < 1:
            days_limit = 5
    except ValueError:
        days_limit = 5
    cutoff_ts = time.time() - days_limit * 24 * 60 * 60

    for feed_url in feed_urls:
        try:
            parsed_feed = feedparser.parse(feed_url)
        except Exception as exc:
            sys.stderr.write(f"Error parsing feed {feed_url}: {exc}\n")
            continue
        feed_title = parsed_feed.feed.get("title", "Unknown Podcast")
        for entry in parsed_feed.entries:
            # Extract article links from the description
            description = entry.get("description") or entry.get("summary") or ""
            article_links = extract_article_links(description)
            if not article_links:
                continue
            # Determine publication date for this entry
            if entry.get("published_parsed"):
                pub_struct = entry.published_parsed
                pub_date = email.utils.formatdate(time.mktime(pub_struct), usegmt=True)
                # Skip items published before the cutoff date
                entry_ts = time.mktime(pub_struct)
                if entry_ts < cutoff_ts:
                    continue
            else:
                # Fallback to current time if no date available
                pub_date = email.utils.formatdate(time.time(), usegmt=True)
                # For entries without a published date, include them only if
                # they were just scraped (i.e. treat them as current)
                entry_ts = time.time()
            for title_text, href in article_links:
                item_desc = f"Article mentioned in '{entry.title}' from {feed_title}."
                all_items.append(
                    {
                        "title": title_text,
                        "link": href,
                        "pubDate": pub_date,
                        "description": item_desc,
                    }
                )
            episodes.append(
                {
                    "podcast": feed_title,
                    "episode": entry.title,
                    "pubDate": pub_date,
                    "links": [
                        {"title": t, "url": u} for t, u in article_links
                    ],
                }
            )

    # Sort items by publication date descending (newest first)
    # Items have pubDate strings in RFC 822 format, parse them back to timestamps
    def parse_pubdate(pubdate: str) -> float:
        try:
            return email.utils.parsedate_to_datetime(pubdate).timestamp()
        except Exception:
            return 0.0

    all_items.sort(key=lambda x: parse_pubdate(x["pubDate"]), reverse=True)
    episodes.sort(key=lambda x: parse_pubdate(x["pubDate"]), reverse=True)

    # Build the feed XML
    rss_xml = build_rss_channel(all_items)

    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "generated_feed.xml")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    print(f"Generated feed written to {output_path}")

    generate_html_pages(episodes, output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
