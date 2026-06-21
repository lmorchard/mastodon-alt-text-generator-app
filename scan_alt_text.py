#!/usr/bin/env python3
"""
Scan recent Mastodon posts for images missing alt text, generate descriptions
via OpenAI, and update the posts automatically.

Intended for unattended crontab use; exits 0 on success, 2 if any images
failed to update.

Required env vars (or set in .env):
  MASTODON_ACCESS_TOKEN   — your Mastodon user access token
  MASTODON_BASE_URL       — e.g. https://mastodon.social
  MASTODON_CLIENT_ID      — from your registered app
  MASTODON_CLIENT_SECRET  — from your registered app
  OPENAI_API_KEY          — OpenAI (or compatible) API key

Optional:
  OPENAI_BASE_URL         — override API endpoint (e.g. for local LLM)
  ALT_TEXT_LLM_MODEL      — model name (default: gpt-4o-mini)
"""

import argparse
import base64
import ipaddress
import logging
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

import requests
import openai
from mastodon import Mastodon, MastodonAPIError

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%dT%H:%M:%S',
)
log = logging.getLogger(__name__)

ALLOWED_MEDIA_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
ALT_TEXT_MAX_LENGTH = 1500
PAGE_SIZE = 40


# ---------------------------------------------------------------------------
# Helpers (kept standalone so this script has no dependency on app.py)
# ---------------------------------------------------------------------------

def _safe_image_url(url):
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = parsed.hostname or ''
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    except ValueError:
        if hostname.lower() in ('localhost', ''):
            return False
    return True


def _get_mastodon_client(access_token):
    return Mastodon(
        client_id=os.environ.get('MASTODON_CLIENT_ID'),
        client_secret=os.environ.get('MASTODON_CLIENT_SECRET'),
        access_token=access_token,
        api_base_url=os.environ.get('MASTODON_BASE_URL'),
    )


def _get_openai_client():
    return openai.OpenAI(
        api_key=os.environ.get('OPENAI_API_KEY'),
        base_url=os.environ.get('OPENAI_BASE_URL'),
    )


def _fetch_image_b64(image_url):
    """Return (base64_string, media_type) for the image at image_url."""
    resp = requests.get(image_url, timeout=15)
    resp.raise_for_status()
    media_type = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
    if media_type not in ALLOWED_MEDIA_TYPES:
        media_type = 'image/jpeg'
    return base64.b64encode(resp.content).decode('utf-8'), media_type


def _generate_alt_text(client, image_b64, media_type):
    response = client.chat.completions.create(
        model=os.environ.get('ALT_TEXT_LLM_MODEL', 'gpt-4o-mini'),
        messages=[{
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {'url': f'data:{media_type};base64,{image_b64}'},
                },
                {
                    'type': 'text',
                    'text': (
                        'Generate concise, descriptive alt text for this image. '
                        'Focus on the key visual elements and purpose of the image. '
                        'Keep it under 125 characters when possible.'
                    ),
                },
            ],
        }],
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()[:ALT_TEXT_MAX_LENGTH]


def _update_media_alt_text(mastodon, post_id, media_id, alt_text):
    source = mastodon.status_source(post_id)
    status = mastodon.status(post_id)

    media_attributes = []
    found = False
    for att in status['media_attachments']:
        mid = str(att['id'])
        media_attributes.append({
            'id': mid,
            'description': alt_text if mid == str(media_id) else (att.get('description') or ''),
        })
        if mid == str(media_id):
            found = True

    if not found:
        raise ValueError(f'Media {media_id} not found in post {post_id}')

    mastodon.status_update(
        post_id,
        status=source.get('text', ''),
        media_attributes=media_attributes,
        spoiler_text=source.get('spoiler_text', ''),
        sensitive=status.get('sensitive', False),
    )


def _iter_recent_statuses(mastodon, account_id, limit, cutoff):
    """Yield statuses newest-first, stopping at limit or cutoff datetime."""
    fetched = 0
    page = mastodon.account_statuses(account_id, limit=PAGE_SIZE)
    while page:
        for status in page:
            if cutoff and status['created_at'] < cutoff:
                return
            yield status
            fetched += 1
            if limit and fetched >= limit:
                return
        page = mastodon.fetch_next(page)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Generate and apply alt text to recent Mastodon images missing it.',
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--limit', type=int, default=15, metavar='N',
        help='Scan the N most recent posts (default: 15)',
    )
    group.add_argument(
        '--since-hours', type=float, metavar='H',
        help='Scan posts from the last H hours (e.g. 48)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Generate alt text but do not update Mastodon',
    )
    parser.add_argument(
        '--token', metavar='TOKEN',
        help='Mastodon access token (overrides MASTODON_ACCESS_TOKEN env var)',
    )
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    access_token = args.token or os.environ.get('MASTODON_ACCESS_TOKEN')
    if not access_token:
        log.error(
            'No Mastodon access token. '
            'Set MASTODON_ACCESS_TOKEN in .env or pass --token.'
        )
        sys.exit(1)

    for var in ('MASTODON_BASE_URL', 'MASTODON_CLIENT_ID', 'MASTODON_CLIENT_SECRET'):
        if not os.environ.get(var):
            log.error('Missing required env var: %s', var)
            sys.exit(1)

    if not os.environ.get('OPENAI_API_KEY') and not os.environ.get('OPENAI_BASE_URL'):
        log.error('No OpenAI credentials. Set OPENAI_API_KEY (and optionally OPENAI_BASE_URL).')
        sys.exit(1)

    mastodon = _get_mastodon_client(access_token)
    openai_client = _get_openai_client()

    try:
        account = mastodon.me()
    except Exception as e:
        log.error('Could not connect to Mastodon: %s', e)
        sys.exit(1)

    log.info('Connected as @%s on %s', account['username'], os.environ.get('MASTODON_BASE_URL'))
    if args.dry_run:
        log.info('[dry-run] No changes will be made to Mastodon.')

    cutoff = None
    limit = None
    if args.since_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=args.since_hours)
        log.info('Scanning posts since %s (%.1f hours)', cutoff.strftime('%Y-%m-%d %H:%M UTC'), args.since_hours)
    else:
        limit = args.limit
        log.info('Scanning last %d posts', limit)

    scanned = updated = skipped = errors = 0

    for status in _iter_recent_statuses(mastodon, account['id'], limit, cutoff):
        scanned += 1
        missing = [
            img for img in status.get('media_attachments', [])
            if img['type'] in ('image', 'gifv') and not img.get('description')
        ]
        if not missing:
            continue

        post_url = status.get('url') or status['id']
        log.info('Post %s — %d image(s) missing alt text', post_url, len(missing))

        for img in missing:
            img_url = img['url']

            if not _safe_image_url(img_url):
                log.warning('  Skipping disallowed URL: %s', img_url)
                skipped += 1
                continue

            try:
                log.info('  Fetching %s', img_url)
                image_b64, media_type = _fetch_image_b64(img_url)

                alt_text = _generate_alt_text(openai_client, image_b64, media_type)
                log.info('  Alt text: %s', alt_text)

                if args.dry_run:
                    log.info('  [dry-run] Skipping update for media %s', img['id'])
                    skipped += 1
                else:
                    _update_media_alt_text(mastodon, status['id'], img['id'], alt_text)
                    log.info('  Updated media %s on post %s', img['id'], status['id'])
                    updated += 1

            except MastodonAPIError as e:
                log.error('  Mastodon API error (media %s): %s', img['id'], e)
                errors += 1
            except Exception as e:
                log.error('  Failed (media %s): %s', img['id'], e)
                errors += 1

    log.info(
        'Finished. Posts scanned: %d | Images updated: %d | Skipped: %d | Errors: %d',
        scanned, updated, skipped, errors,
    )
    sys.exit(2 if errors else 0)


if __name__ == '__main__':
    main()
