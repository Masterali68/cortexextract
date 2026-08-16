from services.cleaner import DomCleaner, extract_title

HTML = """<!DOCTYPE html>
<html>
<head><title>Clean Title</title></head>
<body>
<script>var x = 1;</script>
<style>body { color: red; }</style>
<nav><a href="/home">Home</a></nav>
<footer><p>(c) 2026</p></footer>
<aside class="ad"><img src="https://tracker.example.com/pixel.gif" alt="ad"></aside>
<div id="cookie-banner"><p>Accept cookies</p></div>
<main>
<h1>Article Heading</h1>
<p>First paragraph with <strong>bold</strong> text.</p>
<table><thead><tr><th>K</th><th>V</th></tr></thead><tbody><tr><td>a</td><td>b</td></tr></tbody></table>
<pre><code>const n = 1;</code></pre>
<img src="/logo.png?utm_source=nav&gclid=xyz" alt="Logo">
</main>
</body>
</html>"""


def test_strips_noise_tags():
    markdown = DomCleaner().clean(HTML, strip_noise=True)
    assert "<script>" not in markdown
    assert "Home" not in markdown
    assert "Accept cookies" not in markdown
    assert "(c) 2026" not in markdown
    assert "pixel.gif" not in markdown


def test_preserves_content_and_gfm():
    markdown = DomCleaner().clean(HTML, strip_noise=True)
    assert "Article Heading" in markdown
    assert "First paragraph with" in markdown
    assert "| K | V |" in markdown  # GFM table
    assert "const n = 1;" in markdown  # code block
    assert "![Logo](/logo.png)" in markdown  # alt text + tracking params stripped


def test_strip_noise_false_keeps_headers():
    markdown = DomCleaner().clean(HTML, strip_noise=False)
    assert "Home" in markdown


def test_extract_title_from_tag():
    assert extract_title("<title>Custom Title</title>") == "Custom Title"


def test_ambiguous_class_names_never_strip_content():
    html = """<main>
    <div class="read-along">Reading along content</div>
    <div class="adventure">An adventure story</div>
    <div class="price-tracker">Price tracker table</div>
    <div class="banner">Important banner headline</div>
    </main>"""
    markdown = DomCleaner().clean(html, strip_noise=True)
    assert "Reading along content" in markdown
    assert "An adventure story" in markdown
    assert "Price tracker table" in markdown
    assert "Important banner headline" in markdown


def test_real_noise_markers_still_stripped():
    html = """<div class="cookie-consent">Cookie popup</div>
    <div id="onetrust-banner-sdk">Consent</div>
    <iframe src="https://partner.googleadservices.com/pagead"></iframe>
    <div class="newsletter-signup"><form><input></form></div>
    <div class="ad-slot"><img src="https://ad.server/banner.gif"></div>"""
    markdown = DomCleaner().clean(html, strip_noise=True)
    assert "Cookie popup" not in markdown
    assert "Consent" not in markdown
    assert "googleadservices" not in markdown
    assert "newsletter-signup" not in markdown


def test_contact_info_survives_noise_stripping():
    html = """<nav>Menu</nav>
    <footer>
      <p>Careers</p>
      <a href="mailto:careers@careerco.com">careers@careerco.com</a>
      <p>Call us: +1 (415) 555-0199</p>
    </footer>
    <main><h1>Career Copilot</h1><p>Find the right job faster.</p></main>"""
    markdown = DomCleaner().clean(html, strip_noise=True)
    assert "Menu" not in markdown          # footer/nav chrome still stripped
    assert "careers@careerco.com" in markdown  # email preserved
    assert "415" in markdown                   # phone preserved
    assert "Career Copilot" in markdown


def test_plain_text_email_preserved_without_mailto():
    html = """<footer><p>Reach the team at hello@plaintext.io for any questions.</p></footer>
    <main><h1>Page</h1></main>"""
    markdown = DomCleaner().clean(html, strip_noise=True)
    assert "hello@plaintext.io" in markdown
    assert "## Contact" in markdown
    assert "hello@plaintext.io" in markdown.split("## Contact")[1]


def test_no_contact_junk_when_only_numbers_present():
    html = """<footer><p>Copyright 2001-2026. See stats 34 55 89 144.</p></footer>
    <main><h1>Page</h1></main>"""
    markdown = DomCleaner().clean(html, strip_noise=True)
    assert "## Contact" not in markdown  # years / number lists are not contacts
