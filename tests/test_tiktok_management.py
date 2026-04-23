from __future__ import annotations

import pytest

from ads_agent.agent.nodes.tiktok_common import TikTokContext
from ads_agent.config import Store
from ads_agent.tiktok.client import normalize_campaign_operation


def test_normalize_campaign_operation_aliases():
    assert normalize_campaign_operation('enable') == 'ENABLE'
    assert normalize_campaign_operation('paused') == 'DISABLE'
    assert normalize_campaign_operation('OPERATION_STATUS_ENABLE') == 'ENABLE'


@pytest.mark.asyncio
async def test_tiktok_pixels_node_formats_rows(monkeypatch):
    import ads_agent.agent.nodes.tiktok_pixels as mod

    store = Store(
        slug='demo',
        brand='Demo Store',
        shop_domain='demo.myshopify.com',
        custom_app='demo',
        meta_ad_account=None,
        currency='USD',
    )

    async def fake_load_context(slug: str):
        assert slug == 'demo'
        return (
            TikTokContext(
                store=store,
                advertiser_id='123',
                country='US',
                access_token='token',
                auth_source='oauth',
            ),
            None,
        )

    async def fake_list_pixels(advertiser_id: str, limit: int, *, access_token: str | None = None):
        assert advertiser_id == '123'
        assert limit == 5
        assert access_token == 'token'
        return {
            'pixels': [
                {
                    'pixel_id': 'px_1',
                    'pixel_name': 'Pixel One',
                    'pixel_code': 'CODE1',
                    'activity_status': 'ACTIVE',
                    'partner_name': 'SHOPIFY',
                    'pixel_setup_mode': 'DEVELOPER',
                    'events': [{'event_type': 'COMPLETE_PAYMENT'}],
                }
            ],
            'page_info': {'total_number': 1},
        }

    monkeypatch.setattr(mod, 'load_tiktok_context', fake_load_context)
    monkeypatch.setattr(mod, 'list_pixels', fake_list_pixels)

    state = await mod.tiktok_pixels_node({'store_slug': 'demo', 'limit': 5})
    reply = state['reply_text']
    assert 'Pixel One' in reply
    assert '`px_1`' in reply
    assert 'events 1' in reply


@pytest.mark.asyncio
async def test_tiktok_campaigns_node_handles_empty(monkeypatch):
    import ads_agent.agent.nodes.tiktok_campaigns as mod

    store = Store(
        slug='demo',
        brand='Demo Store',
        shop_domain='demo.myshopify.com',
        custom_app='demo',
        meta_ad_account=None,
        currency='USD',
    )

    async def fake_load_context(slug: str):
        assert slug == 'demo'
        return (
            TikTokContext(
                store=store,
                advertiser_id='123',
                country='US',
                access_token=None,
                auth_source='env',
            ),
            None,
        )

    async def fake_list_campaigns(advertiser_id: str, limit: int, *, access_token: str | None = None):
        assert advertiser_id == '123'
        assert limit == 3
        assert access_token is None
        return {'campaigns': [], 'page_info': {'total_number': 0}}

    monkeypatch.setattr(mod, 'load_tiktok_context', fake_load_context)
    monkeypatch.setattr(mod, 'list_campaigns', fake_list_campaigns)

    state = await mod.tiktok_campaigns_node({'store_slug': 'demo', 'limit': 3})
    assert 'No campaigns found' in state['reply_text']
