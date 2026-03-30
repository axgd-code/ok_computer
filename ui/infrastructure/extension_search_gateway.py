import re

import requests

import app_config as cfg


class ExtensionSearchGateway:
    def search(self, query):
        results = {'chrome': [], 'firefox': []}
        if not query:
            return results

        def _chrome_extension_metadata(ext_id):
            meta = {
                'id': ext_id,
                'name': ext_id,
                'publisher': '',
                'url': f'https://chrome.google.com/webstore/detail/{ext_id}',
            }
            try:
                url = f'https://chrome.google.com/webstore/detail/{ext_id}?hl=en'
                response = requests.get(url, timeout=cfg.ROUTE_EXT_CHROME_METADATA_TIMEOUT_SEC, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code != 200 or not response.text:
                    return meta

                page = response.text
                match_jsonld = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>\s*(\{.*?\})\s*</script>', page, re.S | re.I)
                if match_jsonld:
                    try:
                        import json
                        from html import unescape

                        payload = json.loads(match_jsonld.group(1))
                        name = payload.get('name')
                        if isinstance(name, str) and name.strip():
                            meta['name'] = unescape(name.strip())
                        author = payload.get('author')
                        if isinstance(author, dict):
                            publisher = author.get('name')
                            if isinstance(publisher, str) and publisher.strip():
                                meta['publisher'] = unescape(publisher.strip())
                        elif isinstance(author, list) and author:
                            first = author[0]
                            if isinstance(first, dict):
                                publisher = first.get('name')
                                if isinstance(publisher, str) and publisher.strip():
                                    meta['publisher'] = unescape(publisher.strip())
                    except Exception:
                        pass

                if not meta['name'] or meta['name'] == ext_id:
                    match_og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', page, re.I)
                    if match_og:
                        from html import unescape
                        meta['name'] = unescape(match_og.group(1).replace(' - Chrome Web Store', '').strip())

                if not meta['publisher']:
                    match_pub = re.search(r'Offered\s+by\s*</[^>]+>\s*<[^>]+>([^<]+)<', page, re.I)
                    if match_pub:
                        from html import unescape
                        meta['publisher'] = unescape(match_pub.group(1).strip())
            except Exception:
                pass
            return meta

        try:
            response = requests.get(
                'https://addons.mozilla.org/api/v5/addons/search/',
                params={'q': query, 'page_size': cfg.ROUTE_EXT_FIREFOX_PAGE_SIZE},
                timeout=cfg.ROUTE_EXT_FIREFOX_SEARCH_TIMEOUT_SEC,
            )
            if response.status_code == 200:
                payload = response.json()
                for item in payload.get('results', [])[: cfg.ROUTE_EXT_CHROME_RESULTS_LIMIT]:
                    name = item.get('name')
                    if isinstance(name, dict):
                        name = name.get('en-US') or next((value for value in name.values() if isinstance(value, str) and value.strip()), '')
                    authors = item.get('authors') or []
                    publisher = ''
                    if isinstance(authors, list) and authors:
                        first = authors[0]
                        if isinstance(first, dict):
                            publisher = first.get('name') or ''
                    if isinstance(publisher, dict):
                        publisher = publisher.get('en-US') or next((value for value in publisher.values() if isinstance(value, str) and value.strip()), '')
                    results['firefox'].append({
                        'slug': item.get('slug'),
                        'name': name or item.get('slug') or '',
                        'publisher': publisher,
                        'url': item.get('url'),
                    })
        except Exception:
            pass

        try:
            url = f'https://chrome.google.com/webstore/search/{requests.utils.requote_uri(query)}?hl=en'
            response = requests.get(url, timeout=cfg.ROUTE_EXT_CHROME_SEARCH_TIMEOUT_SEC)
            if response.status_code == 200 and response.text:
                from html import unescape

                seen = set()
                for card in re.finditer(r'data-item-id="([a-p0-9]{32})"', response.text):
                    ext_id = card.group(1)
                    if ext_id in seen:
                        continue
                    seen.add(ext_id)
                    chunk = response.text[card.start():card.start() + cfg.ROUTE_EXT_CHROME_CHUNK_SIZE]
                    name = ext_id
                    publisher = ''
                    slug = ''

                    match_href = re.search(r'href="\./detail/([^/\"]+)/([a-p0-9]{32})"', chunk)
                    if match_href:
                        slug = match_href.group(1)

                    match_name = re.search(r'<h2 class="CiI2if">(.*?)</h2>', chunk, re.S)
                    if match_name:
                        name = unescape(re.sub(r'<[^>]+>', '', match_name.group(1)).strip()) or name
                    elif slug:
                        name = slug.replace('-', ' ').strip().title() or name

                    match_pub = re.search(r'<span class="cJI8ee[^\"]*">(.*?)</span>', chunk, re.S)
                    if match_pub:
                        publisher = unescape(re.sub(r'<[^>]+>', '', match_pub.group(1)).strip())

                    results['chrome'].append({
                        'id': ext_id,
                        'name': name,
                        'publisher': publisher,
                        'url': f'https://chrome.google.com/webstore/detail/{ext_id}',
                    })
                    if len(results['chrome']) >= cfg.ROUTE_EXT_CHROME_RESULTS_LIMIT:
                        break

                if not results['chrome']:
                    ids = re.findall(r'/detail/[^/]+/([a-p0-9]{32})', response.text)
                    for ext_id in ids[: cfg.ROUTE_EXT_CHROME_RESULTS_LIMIT]:
                        if ext_id in seen:
                            continue
                        seen.add(ext_id)
                        results['chrome'].append(_chrome_extension_metadata(ext_id))
        except Exception:
            pass

        return results
