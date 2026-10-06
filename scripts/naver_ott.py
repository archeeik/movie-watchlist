"""OTT: 네이버 영화검색의 '보러가기'에서 제공처를 읽는다 → data/status.json 의 ott, ottAt

    python scripts/naver_ott.py            # 개봉 6개월 이내는 매번, 그 이전(재개봉·기획전 포함)은 격주(ISO 주 번호가 짝수인 주)
    python scripts/naver_ott.py --all      # 전부 조회
    python scripts/naver_ott.py --ids 123,456
    python scripts/naver_ott.py --sample 8 --dry   # 고르게 8편만, 저장하지 않고 결과만 출력

저장 형식: ott[id] = {s: "ntv"(구독으로 볼 수 있는 플랫폼 코드), b: 1(어디서든 단품 구매·대여 가능), u: 1(동명 영화일 수 있음)}
  코드: n 넷플릭스, w 왓챠, t 티빙, v 웨이브, d 디즈니+, a 애플TV. 쿠팡플레이·U+tv 등은 플랫폼으로 표시하지 않고 단품 여부에만 반영한다.
알려진 한계: 네이버는 왓챠의 구독 작품 대부분을 '단품'으로만 적는다(2026-10 비교: 구독 65편 중 54편). 사용자 결정으로 그대로 쓴다.
검색 결과의 영화 카드가 같은 작품인지는 카드의 제목과 감독·연도로 확인해 표시(u)만 한다.
"""
import re
import sys
import urllib.parse
from datetime import timedelta

from lxml import html

from common import CollectError, fetch_text, load, log, now_iso, nz, run, save, today, ws

SEARCH = "https://search.naver.com/search.naver?query="
CODES = {"넷플릭스": "n", "왓챠": "w", "티빙": "t", "웨이브": "v", "디즈니+": "d", "Apple TV": "a", "Apple TV+": "a", "애플TV": "a"}
ORDER = "nwtvda"
RECENT_DAYS = 183   # 개봉 후 이 기간까지는 매주 조회, 그 뒤는 격주


def lookup(f):
    """→ None(영화 카드 없음) 또는 {s, b, u} 중 해당하는 것만 담은 dict(제공처가 없으면 빈 dict일 수 있음)"""
    q = f.get("q") or f["t"]
    doc = html.fromstring(fetch_text(SEARCH + urllib.parse.quote("영화 " + q), headers={"Accept-Language": "ko"}, pause=2))
    head = doc.xpath('//div[@data-sense-fr="MVA-FR-001"]')
    if not head:
        return None
    head_text = ws(head[0].text_content())
    years = {int(y) for y in re.findall(r"(?:19|20)\d{2}", head_text)}
    people = ws(" ".join(x.text_content() for x in doc.xpath('//div[@data-sense-fr="MVA-FR-005"]')))
    title_ok = nz(q)[:6] in nz(head_text)
    # 네이버는 제작연도 대신 국내 개봉연도를 적기도 한다
    year_ok = any(abs(y - f["y"]) <= 1 for y in years) or (bool(f.get("d")) and int(f["d"][:4]) in years)
    dir_ok = any(d.strip() and d.strip() in people for d in f.get("dir", "").split(","))
    subs, buy = set(), False
    for li in doc.xpath('//ul[contains(@class,"platformList")]/li[.//a[@href]]'):
        name = ws("".join(li.xpath(".//strong//text()"))) or (li.xpath(".//img/@alt") or [""])[0]
        cap = ws(" ".join(li.xpath('.//span[contains(@class,"itemCaption")]//text()')))
        if "단품" in cap or re.search(r"[\d,]+원", cap):
            buy = True
        elif name in CODES:
            subs.add(CODES[name])
    out = {}
    if subs:
        out["s"] = "".join(c for c in ORDER if c in subs)
    if buy:
        out["b"] = 1
    if not (title_ok and (dir_ok or year_ok)):
        out["u"] = 1
    return out


def is_future(f, t):
    d = f.get("d", "")
    return bool(d) and (d + "-01" if len(d) == 7 else d) > t


def main():
    films = load("films.json")
    status = load("status.json", {})
    old = status.get("ott", {})
    t = today().isoformat()
    released = [f for f in films if not is_future(f, t)]
    cutoff = (today() - timedelta(days=RECENT_DAYS)).isoformat()
    recent = lambda f: bool(f.get("d")) and (f["d"] + "-31")[:10] >= cutoff
    old_turn = "--all" in sys.argv or today().isocalendar().week % 2 == 0
    targets = [f for f in released if old_turn or recent(f)]
    if "--ids" in sys.argv:
        want = set(sys.argv[sys.argv.index("--ids") + 1].split(","))
        targets = [f for f in released if str(f["id"]) in want]
    if "--sample" in sys.argv:
        n = int(sys.argv[sys.argv.index("--sample") + 1])
        targets = released[::max(1, len(released) // n)][:n]
    dry = "--dry" in sys.argv
    log(f"조회 대상 {len(targets)}편(개봉작 {len(released)}편 중)")

    new, failed, nocard = dict(old), 0, 0
    for f in targets:
        k = str(f["id"])
        try:
            r = lookup(f)
        except CollectError as e:
            failed += 1
            log(f"조회 실패(이전 값 유지): {f['t']} — {e}")
            if failed > max(5, len(targets) // 10):
                raise CollectError("네이버 검색 조회 실패가 너무 많음 — 차단됐거나 구조가 바뀐 것 같음")
            continue
        if r is None:   # 영화 카드가 안 나온 경우: 이전 값을 그대로 둔다
            nocard += 1
            log(f"영화 카드 없음(이전 값 유지): {f['t']}")
            continue
        if dry:
            log(f"- {f['t']} ({f['y']}): {r or '없음'}")
        a = old.get(k, {})
        if not dry and (a.get("s", ""), a.get("b", 0)) != (r.get("s", ""), r.get("b", 0)) and ("s" in a or "b" in a or not a):
            log(f"OTT 변경: {f['t']} {a or '없음'} → {r or '없음'}")
        if r:
            new[k] = r
        else:
            new.pop(k, None)
    if len(targets) >= 10 and nocard > len(targets) * 0.4:
        raise CollectError(f"영화 카드를 못 읽은 작품이 {nocard}/{len(targets)}편 — 구조가 바뀐 것 같음(저장하지 않음)")
    summary = (f"구독 {sum(1 for v in new.values() if v.get('s'))}편, 단품 가능 {sum(1 for v in new.values() if v.get('b'))}편, "
               f"동명 주의 {sum(1 for v in new.values() if v.get('u'))}편, 조회 실패 {failed}, 카드 없음 {nocard}")
    if dry:
        log("저장하지 않음(--dry): " + summary)
        return
    status.update(ott=new, ottAt=now_iso())
    status.pop("nfxAt", None)
    save("status.json", status, depth=2)
    log("저장: " + summary)


if __name__ == "__main__":
    run(main)
