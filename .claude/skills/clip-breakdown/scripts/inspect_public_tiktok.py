#!/usr/bin/env python3
"""Inspect public TikTok HTML, Thai platform captions and covers. No video/cookies/login."""
import argparse
import concurrent.futures
import html
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
MAX_PAGE = 8 * 1024 * 1024
MAX_ASSET = 16 * 1024 * 1024


def read_url(url, limit):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Response exceeds inspection size limit')
        return data, response.geturl()


def extract_item(page):
    match = re.search(r'<script\b[^>]*\bid=[\"\x27]__UNIVERSAL_DATA_FOR_REHYDRATION__[\"\x27][^>]*>(.*?)</script>', page, re.S)
    if not match:
        raise ValueError('Public page has no expected video metadata; browser rendering or access may be required')
    state = json.loads(match.group(1))
    detail = state.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {})
    item = detail.get('itemInfo', {}).get('itemStruct')
    if not isinstance(item, dict) or not item.get('id'):
        raise ValueError('Public metadata does not contain a video item')
    return item


def inspect(url, out_dir):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not (host == 'tiktok.com' or host.endswith('.tiktok.com')) or parsed.username or parsed.password:
        raise ValueError('Provide a public HTTPS TikTok page URL without credentials')
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    raw, canonical = read_url(url, MAX_PAGE)
    item = extract_item(raw.decode('utf-8'))
    video = item.get('video', {})
    evidence = {
        'source_url': url, 'canonical_url': canonical,
        'item_id': item['id'], 'author': item.get('author', {}).get('uniqueId'),
        'duration_seconds_platform': video.get('duration'), 'description': item.get('desc', ''),
        'evidence': {'metadata': True, 'thai_platform_captions': False, 'cover_downloaded': False,
                     'video_viewed': False, 'audio_listened': False},
        'warnings': ['Platform captions may contain ASR errors. Downloaded cover still needs visual inspection.'],
        'files': {},
    }
    assets = []
    thai = next((s for s in video.get('subtitleInfos', []) if s.get('LanguageCodeName') == 'tha-TH'), None)
    if thai and thai.get('Url'):
        assets.append(('thai-captions.vtt', thai['Url'], 'thai_platform_captions'))
    if video.get('cover'):
        assets.append(('cover.image', video['cover'], 'cover_downloaded'))
    def asset(task):
        name, asset_url, key = task
        try:
            content, _ = read_url(asset_url, MAX_ASSET)
            if name.endswith('.vtt') and not content.lstrip(b'\xef\xbb\xbf\r\n ').startswith(b'WEBVTT'):
                raise ValueError('Caption response is not WEBVTT')
            target = out_dir / name
            target.write_bytes(content)
            return key, name, None
        except (urllib.error.URLError, ValueError, OSError) as error:
            return key, name, str(error)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for key, name, error in pool.map(asset, assets):
            if error:
                evidence['warnings'].append(name + ': ' + error)
            else:
                evidence['evidence'][key] = True
                evidence['files'][key] = name
    (out_dir / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--out-dir', required=True, help='A new directory; existing output is never overwritten')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.url, args.out_dir), ensure_ascii=False, indent=2))
    except (urllib.error.URLError, ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, 'Inspection incomplete: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
