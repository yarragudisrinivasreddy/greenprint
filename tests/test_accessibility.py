"""Accessibility contract of the served interface."""
from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def page(client: Any) -> str:
    return str(client.get("/").get_data(as_text=True))


class TestPageAccessibility:
    def test_document_declares_language(self, page: str) -> None:
        assert '<html lang="en">' in page

    def test_skip_link_targets_main_content(self, page: str) -> None:
        assert 'class="skip-link"' in page and 'href="#main-content"' in page

    def test_aria_landmarks_present(self, page: str) -> None:
        for landmark in ('role="main"', 'role="navigation"', 'role="banner"', 'role="contentinfo"'):
            assert landmark in page

    def test_live_regions_for_dynamic_results(self, page: str) -> None:
        assert page.count('aria-live="polite"') >= 3

    def test_every_form_control_is_labelled(self, page: str) -> None:
        for control_id in ("language-select", "activity-text", "scenario-text"):
            assert f'for="{control_id}"' in page

    def test_buttons_carry_aria_labels(self, page: str) -> None:
        assert 'aria-label="Estimate carbon footprint"' in page
        assert 'aria-label="Run what-if simulation"' in page

    def test_no_inline_styles_or_handlers(self, page: str) -> None:
        # CSP forbids inline styling/scripting; the template must comply.
        assert "style=" not in page and "onclick=" not in page

    def test_stylesheet_supports_reduced_motion_and_dark_mode(self, client: Any) -> None:
        css = client.get("/static/css/styles.css").get_data(as_text=True)
        assert "prefers-reduced-motion" in css
        assert "prefers-color-scheme: dark" in css
        assert "forced-colors" in css
        assert ":focus-visible" in css
