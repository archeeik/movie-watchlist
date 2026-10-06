"""네이버 영화검색의 '보러가기'에서 OTT 제공처를 읽는다. (시험 단계: 저장하지 않고 지금 데이터와 비교만 한다)

    python scripts/naver_ott.py --sample 20     # 개봉작 중 고르게 20편을 조회해 status.json의 넷플릭스·왓챠 값과 비교
    python scripts/naver_ott.py --ids 123,456

검색 결과의 영화 카드가 같은 작품인지(동명 영화)는 카드의 제작연도·감독으로 확인해 '불확실' 표시만 한다.
"""
import re
import sys
import urllib.parse

from lxml import html

from common import CollectError, fetch_text, load, log, nz, run, today, ws

SEARCH = "https://search.naver.com/search.naver?query="
CODES = {"넷플릭스": "n", "왓챠": "w", "티빙": "t", "웨이브": "v", "쿠팡플레이": "c", "디즈니+": "d", "Apple TV": "a", "애플TV": "a"}


def lookup(f):
    """→ None(영화 카드 없음) 또는 {title, year, sure, offers: {코드 또는 이름: {k: 's'|'b', p, href}}}"""
    q = "영화 " + (f.get("q") or f["t"])
    doc = html.fromstring(fetch_text(SEARCH + urllib.parse.quote(q), headers={"Accept-Language": "ko"}, pause=2))
    head = doc.xpath('//div[@data-sense-fr="MVA-FR-001"]')
    if not head:
        return None
    head_text = ws(head[0].text_content())
    year = re.search(r"(19|20)\d{2}", head_text)
    people = ws(" ".join(x.text_content() for x in doc.xpath('//div[@data-sense-fr="MVA-FR-005"]')))
    dirs = [d.strip() for d in f.get("dir", "").split(",") if d.strip()]
    title_ok = nz(head_text).startswith(nz(f.get("q") or f["t"])[:6])
    year_ok = bool(year) and abs(int(year.group()) - f["y"]) <= 1
    dir_ok = any(d in people for d in dirs)
    offers = {}
    for li in doc.xpath('//ul[contains(@class,"platformList")]/li[.//a[@href]]'):
        name = ws("".join(li.xpath(".//strong//text()"))) or (li.xpath(".//img/@alt") or [""])[0]
        cap = ws(" ".join(li.xpath('.//span[contains(@class,"itemCaption")]//text()')))
        price = re.search(r"[\d,]+원", cap)
        o = {"k": "b" if "단품" in cap or price else "s", "href": li.xpath(".//a/@href")[0]}
        if price:
            o["p"] = price.group()
        offers.setdefault(CODES.get(name, name), o)
    return {"title": head_text[:40], "year": year.group() if year else "", "sure": title_ok and (dir_ok or year_ok), "offers": offers}


def main():
    films = load("films.json")
    old = load("status.json", {}).get("ott", {})
    t = today().isoformat()
    released = [f for f in films if not (f.get("d") and (f["d"] + "-01" if len(f["d"]) == 7 else f["d"]) > t)]
    if "--ids" in sys.argv:
        want = set(sys.argv[sys.argv.index("--ids") + 1].split(","))
        targets = [f for f in released if str(f["id"]) in want]
    else:
        n = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 20
        targets = released[::max(1, len(released) // n)][:n]
    stat = {"카드 없음": 0, "불확실": 0, "넷플릭스 일치": 0, "넷플릭스 다름": 0, "왓챠 일치": 0, "왓챠 다름": 0}
    for f in targets:
        r = lookup(f)
        o = old.get(str(f["id"]), {})
        if r is None:
            stat["카드 없음"] += 1
            log(f"- {f['t']} ({f['y']}): 영화 카드 없음 | 지금 값 n={o.get('n', '-')} w={o.get('w', '-')}")
            continue
        if not r["sure"]:
            stat["불확실"] += 1
        nv = r["offers"]
        n_new, w_new = ("s" if "n" in nv else ""), nv.get("w", {}).get("k", "")
        wid = re.search(r"watcha\.com/contents/(\w+)", nv.get("w", {}).get("href", ""))
        stat["넷플릭스 일치" if n_new == o.get("n", "") else "넷플릭스 다름"] += 1
        stat["왓챠 일치" if w_new == o.get("w", "") else "왓챠 다름"] += 1
        shown = ", ".join(f"{k}:{v['k']}" + (f"({v['p']})" if v.get("p") else "") for k, v in nv.items()) or "없음"
        log(f"- {f['t']} ({f['y']}){'' if r['sure'] else ' [불확실: ' + r['title'] + ']'}: {shown}"
            f" | 지금 값 n={o.get('n', '-')} w={o.get('w', '-')}"
            + ("" if n_new == o.get("n", "") and w_new == o.get("w", "") else "  ← 다름")
            + (f" | wid {'같음' if wid and wid.group(1) == o.get('wid') else '다름'}" if wid and o.get("wid") else ""))
    log(f"요약({len(targets)}편): " + ", ".join(f"{k} {v}" for k, v in stat.items()))
    if targets and stat["카드 없음"] == len(targets):
        raise CollectError("네이버 검색에서 영화 카드를 하나도 읽지 못함 — 차단됐거나 구조가 바뀐 것 같음")


if __name__ == "__main__":
    run(main)
