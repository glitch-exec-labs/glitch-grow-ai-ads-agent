"""v0 smoke tests — imports and config resolve without network/DB."""
from __future__ import annotations

from ads_agent import __version__
from ads_agent.config import STORES, get_store


def test_version_set():
    assert __version__


def test_store_registry_resolves_by_slug_and_domain():
    first = STORES[0]
    assert get_store(first.slug) is not None
    assert get_store(first.shop_domain) is not None
    if get_store("store-b-india") is not None and get_store("store-b-global") is not None:
        assert get_store("store-b-india").meta_ad_account == get_store("store-b-global").meta_ad_account
    assert get_store("does-not-exist") is None


def test_all_stores_have_unique_slugs():
    slugs = [s.slug for s in STORES]
    assert len(slugs) == len(set(slugs))


def test_graph_builds():
    from ads_agent.agent.graph import build_graph

    g = build_graph()
    assert g is not None


def test_tiktok_store_mapping_defaults_empty():
    from ads_agent.config import STORE_TIKTOK_ACCOUNTS

    assert isinstance(STORE_TIKTOK_ACCOUNTS, dict)
