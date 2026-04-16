"""v0 smoke tests — imports and config resolve without network/DB."""
from __future__ import annotations

from ads_agent import __version__
from ads_agent.config import STORES, get_store


def test_version_set():
    assert __version__


def test_store_registry_resolves_by_slug_and_domain():
    assert get_store("store-a") is not None
    assert get_store("your-store-a.myshopify.com") is not None
    # stores sharing an ad account return the same act_ string
    assert get_store("store-b-india").meta_ad_account == get_store("store-b-global").meta_ad_account
    assert get_store("does-not-exist") is None


def test_all_stores_have_unique_slugs():
    slugs = [s.slug for s in STORES]
    assert len(slugs) == len(set(slugs))


def test_graph_builds():
    from ads_agent.agent.graph import build_graph

    g = build_graph()
    assert g is not None
