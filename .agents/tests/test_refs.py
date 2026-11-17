from __future__ import annotations

import pytest
from tj_work_items.refs import ItemRef, parse_ref


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("HTTPS://Tracker.Example:443/items/42", "url:https://tracker.example/items/42"),
        ("https://Tracker.Example:8443/items/42?q=x#c", "url:https://tracker.example:8443/items/42?q=x#c"),
        ("https://tracker.example", "url:https://tracker.example/"),
        ("https://tracker.example/a/../42", "url:https://tracker.example/42"),
        ("https://tracker.example/42?", "url:https://tracker.example/42?"),
        ("https://tracker.example/42#", "url:https://tracker.example/42#"),
        ("https://[::1]:8443/42", "url:https://[::1]:8443/42"),
        ("custom://tracker.example/42", "url:custom://tracker.example/42"),
        ("https://tracker.example:8443", "url:https://tracker.example:8443/"),
        ("jira:tracker.example:ABC-1:subtask", "jira:tracker.example:ABC-1:subtask"),
    ],
)
def test_opaque_reference_round_trips_store_contract(text: str, canonical: str) -> None:
    parsed = parse_ref(text, None)
    assert str(parsed) == canonical
    assert parse_ref(canonical, None) == parsed


@pytest.mark.parametrize(
    "text",
    [
        "https://",
        "https:/tracker.example/42",
        "url:not-an-absolute-url",
        "https://tracker.example:bad/42",
        "https://tracker.example:99999/42",
        "https://[invalid/42",
        "https://tracker example/42",
        "https://tracker.example/a\nb",
        "https://tracker.example\\42",
        "https://%zz/42",
    ],
)
def test_malformed_urls_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match=r"URL|port|Port|Invalid|absolute"):
        parse_ref(text, None)


def test_explicit_reference_never_uses_the_default_provider() -> None:
    assert parse_ref("custom:tracker.example/team:ABC-1", ("github", "github.com/owner/repo")) == ItemRef(
        "custom", "tracker.example/team", "ABC-1"
    )
