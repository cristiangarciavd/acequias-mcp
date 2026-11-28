"""Checks on the player rulebook site under site/ (#195)."""

import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
PAGES = {
    "reglas": ("es", "acequias-reglas.pdf"),
    "rules": ("en", "acequias-rules.pdf"),
}


def _page(name):
    return (SITE / name / "index.html").read_text(encoding="utf-8")


def _ids(html):
    return re.findall(r'\bid="([^"]+)"', html)


def test_rulebooks_share_the_same_ids_in_the_same_order():
    es, en = _ids(_page("reglas")), _ids(_page("rules"))
    assert es == en
    for section in ("components", "setup", "turn", "water", "planting", "scoring",
                    "cortes", "bodega", "end", "example", "die", "varietals", "sources"):
        assert section in es


@pytest.mark.parametrize("name", PAGES)
def test_rulebook_is_standalone_and_links_its_pdf(name):
    lang, pdf = PAGES[name]
    html = _page(name)
    assert html.startswith("<!doctype html>")
    assert f'<html lang="{lang}">' in html
    assert "<head>" in html and "</head>" in html and "</html>" in html
    assert f'href="{pdf}"' in html
    assert '<link rel="alternate" hreflang="es" href="../reglas/">' in html
    assert '<link rel="alternate" hreflang="en" href="../rules/">' in html
    assert "© 2026 Cristian García" in html
    assert "CC BY-NC-SA 4.0" in html
    assert "@page{size:A4" in html


@pytest.mark.parametrize("name", PAGES)
def test_rulebook_uses_self_hosted_fonts_and_relative_links(name):
    html = _page(name)
    assert "fonts.googleapis" not in html and "fonts.gstatic" not in html
    assert "/acequias-mcp/" not in html
    for font in re.findall(r'url\("\.\./fonts/([^"]+)"\)', html):
        assert (SITE / "fonts" / font).is_file()
    for href in re.findall(r'href="([^"]+)"', html):
        assert href.startswith(("https://", "../", "acequias-")), href


def test_fonts_ship_their_ofl_texts():
    for family in ("Fraunces", "Figtree", "JetBrainsMono"):
        assert (SITE / "fonts" / f"{family}.ttf").is_file()
        ofl = (SITE / "fonts" / f"{family}-OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in ofl


def test_language_picker_links_both_rulebooks():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    for href in ('href="reglas/"', 'href="rules/"',
                 'href="reglas/acequias-reglas.pdf"', 'href="rules/acequias-rules.pdf"'):
        assert href in html
    assert (SITE / ".nojekyll").is_file()


@pytest.mark.parametrize("name", PAGES)
def test_rulebook_matches_rules_v3_numbers(name):
    html = _page(name)
    # Supply and score targets per mode and player count (_docs/rules-v3.md).
    assert re.search(r"Normal</b> · \w+</td><td class=\"n\">14</td><td class=\"n\">14</td>"
                     r"<td class=\"n\">20</td><td class=\"n\">20</td>", html)
    assert re.search(r"Normal</b> · \w+</td><td class=\"n\">50</td><td class=\"n\">50</td>"
                     r"<td class=\"n\">55</td><td class=\"n\">40</td>", html)
    assert re.search(r"Flash</b> · \w+</td><td class=\"n\">30</td><td class=\"n\">35</td>", html)


def test_license_files():
    root = SITE.parent
    lic = (root / "LICENSE").read_text(encoding="utf-8")
    assert lic.startswith("Required Notice: Copyright 2026 Cristian García")
    assert "# PolyForm Noncommercial License 1.0.0" in lic
    game = (root / "LICENSE-GAME.md").read_text(encoding="utf-8")
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode" in game
