from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter, ATX

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}

_NOISE_TAGS = {"script", "style", "nav", "footer", "header", "aside", "iframe"}
# Only strip class/id tokens that unambiguously mark consent/overlay chrome.
# Substring matching is dangerous: "ad-" destroys classes like "read-along",
# "tracking" destroys "price-tracker", and "banner" destroys legit headings.
_NOISE_TOKENS = {
    "cookie",
    "consent",
    "gdpr",
    "modal",
    "overlay",
    "popup",
    "popover",
    "newsletter",
    "advertisement",
    "adsbygoogle",
}
# Ad frames are targeted precisely by their source, never by class names.
_AD_SRC_HINTS = ("doubleclick", "googlesyndication", "adsystem", "adservice")
_NOISE_IDS = (
    "CybotCookiebotDialog",
    "onetrust-banner-sdk",
    "cookie-banner",
    "consent",
    "cookieConsent",
    "cookieBanner",
)


def _is_noise_attr(value: str | list | None) -> bool:
    """True only when a class/id token exactly matches a known noise marker."""
    if not value:
        return False
    if isinstance(value, list):
        lowered = " ".join(str(v) for v in value).lower()
    else:
        lowered = value.lower()
    tokens = set(filter(None, re.split(r"[^a-z0-9]", lowered)))
    return bool(tokens & _NOISE_TOKENS)


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
# Strict phone shape (3-3-4, optional +code / parens area code) + digit-count
# validation below. Looser patterns match years ("2001-2026") and number lists.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
)


def _collect_contacts(soup: BeautifulSoup) -> list[str]:
    """Emails + phone numbers found anywhere in the document (incl. footers).

    Noise stripping removes navbars/footers where contact info usually lives;
    collecting it up front means a "what's the email?" question can still be
    answered instead of the info being destroyed with the chrome.
    """
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.lower().startswith("mailto:"):
            email = href[len("mailto:") :].split("?")[0].strip()
            if email and email.lower() not in seen:
                seen.add(email.lower())
                found.append(email)
    for match in _EMAIL_RE.findall(soup.get_text(" ")):
        if match.lower() not in seen:
            seen.add(match.lower())
            found.append(match)
    for match in _PHONE_RE.findall(soup.get_text(" ")):
        digits = re.sub(r"\D", "", match)
        if (len(digits) == 10 or (len(digits) == 11 and digits[0] == "1")) and match not in seen:
            seen.add(match)
            found.append(match)
    return found


def _strip_tracking_from_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)
    )


class _CleanConverter(MarkdownConverter):
    """Markdownify converter that strips tracking params and keeps alt text."""

    def convert_img(self, el, text, parent_tags):
        alt = el.get("alt", "").strip()
        src = el.get("src", "")
        src = _strip_tracking_from_url(src)
        if alt and src:
            return f"![{alt}]({src})"
        if src:
            return f"![]({src})"
        return ""

    def convert_a(self, el, text, parent_tags):
        href = el.get("href", "")
        href = _strip_tracking_from_url(href)
        return super().convert_a(el, text, parent_tags)


class DomCleaner:
    """Prune structural noise from a raw HTML document and emit GFM markdown."""

    def __init__(self) -> None:
        self._converter = _CleanConverter(heading_style=ATX, bullets="-")

    def clean(self, raw_html: str, strip_noise: bool = True) -> str:
        soup = BeautifulSoup(raw_html, "html.parser")

        contacts: list[str] = []
        if strip_noise:
            contacts = _collect_contacts(soup)
            for tag in soup.find_all(_NOISE_TAGS):
                tag.decompose()

            for tag in soup.find_all(
                lambda el: _is_noise_attr(el.get("class"))
                or _is_noise_attr(el.get("id"))
                or (el.get("id") or "").strip().lower() in _NOISE_IDS
            ):
                tag.decompose()

            for iframe in soup.find_all("iframe"):
                src = (iframe.get("src") or "").lower()
                if any(hint in src for hint in _AD_SRC_HINTS):
                    iframe.decompose()

            for element in soup(["svg", "path", "canvas", "form", "button", "select", "input"]):
                element.decompose()

            for img in soup.find_all("img"):
                src = img.get("src", "").lower()
                if _is_noise_attr(src) or "pixel" in src or src.startswith("data:"):
                    img.decompose()
                    continue
                if "http" not in src and not src.startswith("/") and not src.startswith("."):
                    img.decompose()

        for el in soup.find_all(["a", "img"]):
            attr = "href" if el.name == "a" else "src"
            value = el.get(attr)
            if value:
                el[attr] = _strip_tracking_from_url(value)

        markdown = self._converter.convert_soup(soup)
        if strip_noise and contacts:
            missing = [contact for contact in contacts if contact not in markdown]
            if missing:
                markdown = (
                    markdown.rstrip()
                    + "\n\n## Contact\n\n"
                    + "\n".join(f"- {contact}" for contact in missing)
                    + "\n"
                )
        return markdown


def extract_title(raw_html: str) -> str:
    """Best-effort title extraction from HTML head or metadata."""
    soup = BeautifulSoup(raw_html, "html.parser")
    og_title = soup.find("meta", {"property": "og:title"})
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return re.sub(r"\s+", " ", title_tag.string).strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return ""


def strip_noise(raw_html: str) -> str:
    """Convenience wrapper: run the DOM cleaner and return GFM markdown."""
    return DomCleaner().clean(raw_html)