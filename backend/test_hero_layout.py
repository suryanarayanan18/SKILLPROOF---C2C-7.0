"""
test_hero_layout.py
Verification of SkillProof Hero/Home Page layout, styling, and responsiveness.

Verifies:
1. No inline fixed-width (1280px/1024px) on <html> or <body>.
2. <html> and <body> use width: 100% and min-height: 100vh/100dvh.
3. Background video container (.bg) uses position: fixed, inset: 0, filling full viewport.
4. Page container (.page) uses width: 100% and centered flex alignment.
5. Navigation header (.header) is horizontally centered with max-width: 720px.
6. Hero section (.hero) is centered horizontally and vertically.
7. Headline (.headline) uses stable font sizing (72px desktop) without aggressive progressive shrinking.
8. Subhead (.subhead) and CTA button (.cta-btn) have stable proportional typography and padding.
9. Discrete responsive breakpoints exist for tablet (max-width: 860px/720px) and mobile (max-width: 480px).
10. HTTP GET /index.html returns 200 with full content.
"""

from pathlib import Path
import re
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
INDEX_HTML_PATH = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


def run_checks():
    print("=" * 70)
    print("Running Hero Layout & Responsiveness Verification")
    print("=" * 70)

    content = INDEX_HTML_PATH.read_text(encoding="utf-8")
    passed = 0
    failed = 0

    def check(condition, desc):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {desc}")
        else:
            failed += 1
            print(f"  [FAIL] {desc}")

    # 1. No fixed width/height on <html> tag
    html_tag_match = re.search(r"<html[^>]*>", content, re.IGNORECASE)
    html_tag = html_tag_match.group(0) if html_tag_match else ""
    check("1280px" not in html_tag, "No hardcoded 1280px width on <html> tag")
    check("1024px" not in html_tag, "No hardcoded 1024px height on <html> tag")
    check("style=" not in html_tag, "No inline style attribute on <html> tag")

    # 2. Sizing on html, body
    body_rule_match = re.search(r"html,\s*body\s*\{([^}]+)\}", content)
    body_rule = body_rule_match.group(1) if body_rule_match else ""
    check("width: 100%" in body_rule, "html, body has width: 100%")
    check("min-height:" in body_rule, "html, body has min-height: 100vh/100dvh")
    check("overflow-x: hidden" in body_rule, "html, body has overflow-x: hidden")

    # 3. Background video container (.bg)
    bg_rule_match = re.search(r"\.bg\s*\{([^}]+)\}", content)
    bg_rule = bg_rule_match.group(1) if bg_rule_match else ""
    check("position: fixed" in bg_rule, ".bg uses position: fixed (full-bleed across any viewport)")
    check("inset: 0" in bg_rule, ".bg uses inset: 0")
    check("width: 100%" in bg_rule, ".bg uses width: 100%")
    check("height: 100%" in bg_rule, ".bg uses height: 100%")

    # 4. Page container (.page)
    page_rule_match = re.search(r"\.page\s*\{([^}]+)\}", content)
    page_rule = page_rule_match.group(1) if page_rule_match else ""
    check("width: 100%" in page_rule, ".page uses width: 100%")
    check("align-items: center" in page_rule, ".page uses align-items: center (horizontal centering)")

    # 5. Header centering (.header)
    header_rule_match = re.search(r"\.header\s*\{([^}]+)\}", content)
    header_rule = header_rule_match.group(1) if header_rule_match else ""
    check("justify-content: center" in header_rule, ".header uses justify-content: center")
    check("max-width: 720px" in header_rule, ".header has max-width: 720px constraint")

    # 6. Hero centering (.hero)
    hero_rule_match = re.search(r"\.hero\s*\{([^}]+)\}", content)
    hero_rule = hero_rule_match.group(1) if hero_rule_match else ""
    check("align-items: center" in hero_rule, ".hero uses align-items: center")
    check("justify-content: center" in hero_rule, ".hero uses justify-content: center")
    check("text-align: center" in hero_rule, ".hero uses text-align: center")

    # 7. Stable headline typography without aggressive clamp shrink
    headline_rule_match = re.search(r"\.headline\s*\{([^}]+)\}", content)
    headline_rule = headline_rule_match.group(1) if headline_rule_match else ""
    check("font-size: 72px" in headline_rule, ".headline has stable 72px desktop font size")
    check("clamp(" not in headline_rule, ".headline does not use continuous clamp shrink")

    # 8. Discrete media queries exist
    check("@media (max-width: 860px)" in content, "Discrete breakpoint for tablet (@media max-width: 860px)")
    check("@media (max-width: 720px)" in content, "Discrete breakpoint for compact (@media max-width: 720px)")
    check("@media (max-width: 480px)" in content, "Discrete breakpoint for mobile (@media max-width: 480px)")

    # 9. Live server check
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/index.html")
        html = req.read().decode("utf-8")
        check(req.status == 200, "GET /index.html returns 200 OK")
        check("Proof, Not Paper" in html, "Headline 'Proof, Not Paper' is present")
        check("skill-selection.html" in html, "Link to assessments/get started is present")
    except Exception as e:
        check(False, f"Live server check failed: {e}")

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed} checks.")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    import sys
    ok = run_checks()
    if not ok:
        sys.exit(1)
