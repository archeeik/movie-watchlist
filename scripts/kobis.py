"""상영 상태: KOBIS 일별 박스오피스(최근 8일)의 스크린 수 → data/status.json 의 scr, scrDate, scrAt"""
import http.cookiejar
import re
import urllib.parse
import urllib.request
from datetime import timedelta

from lxml import html

from common import CollectError, fetch_text, load, log, now_iso, nz, run, save, today

URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyBoxOfficeList.do"


def fetch_days():
    """[(날짜 'YYYY-MM-DD', {정규화 제목: 스크린 수})] 최신 날짜부터."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    first = html.fromstring(fetch_text(URL, opener=opener))
    tok = first.xpath('//form[@id="searchForm"]//input[@name="CSRFToken"]/@value')
    if not tok:
        raise CollectError("KOBIS 검색 폼에서 CSRFToken을 찾지 못함 — 구조가 바뀐 것 같음")
    end = today() - timedelta(days=1)
    form = {"CSRFToken": tok[0], "loadEnd": "0", "searchType": "search",
            "sSearchFrom": (end - timedelta(days=7)).isoformat(), "sSearchTo": end.isoformat()}
    doc = html.fromstring(fetch_text(URL, opener=opener, data=urllib.parse.urlencode(form).encode(), headers={"Referer": URL}))
    dates = []
    for e in doc.xpath('//div[contains(@class,"board_tit")]'):
        m = re.search(r"(\d{4})년\s*(\d{2})월\s*(\d{2})일", e.text_content())
        if m:
            dates.append("-".join(m.groups()))
    tables = doc.xpath("//table")
    n = len(dates)
    # 표는 '날짜별 상위 10' n개 뒤에 '날짜별 나머지' n개가 같은 날짜 순서로 온다
    if n == 0 or len(tables) != 2 * n:
        raise CollectError(f"KOBIS 표 구성이 예상과 다름(날짜 {n}개, 표 {len(tables)}개)")
    out = []
    for i, d in enumerate(dates):
        scr = {}
        for tb in (tables[i], tables[i + n]):
            for tr in tb.xpath(".//tbody/tr"):
                td = tr.xpath("./td")
                if len(td) < 4:
                    continue
                title = (td[1].xpath(".//a/@title") or [""])[0] or re.sub(r"(동일|New|\d+\s*(상승|하락))\s*$", "", td[1].text_content().strip())
                try:
                    cnt = int(td[-2].text_content().replace(",", "").strip() or 0)
                except ValueError:
                    raise CollectError(f"KOBIS 스크린 수 칸을 읽지 못함: {td[-2].text_content()!r}")
                k = nz(title)
                if k:
                    scr[k] = max(scr.get(k, 0), cnt)
        out.append((d, scr))
    if sum(len(s) for _, s in out) < 100:
        raise CollectError("KOBIS에서 읽은 작품 수가 너무 적음 — 구조 확인 필요")
    return out


def main():
    films = load("films.json")
    status = load("status.json", {})
    days = fetch_days()
    last_day = days[0][0]
    scr = {}
    for f in films:
        keys = {nz(f["t"]), nz(f.get("q", ""))} - {""}
        cnt = max((days[0][1].get(k, 0) for k in keys), default=0)
        recent = next((d for d, s in days if any(s.get(k, 0) > 0 for k in keys)), "")
        scr[str(f["id"])] = [cnt, recent[5:]]
    old = status.get("scr", {})
    on = lambda v: v and v[0] > 0
    started = [f["t"] for f in films if on(scr[str(f["id"])]) and not on(old.get(str(f["id"])))]
    ended = [f["t"] for f in films if on(old.get(str(f["id"]))) and not on(scr[str(f["id"])])]
    log(f"기준일 {last_day}: 상영중 {sum(1 for v in scr.values() if v[0] > 0)}편, 간헐 {sum(1 for v in scr.values() if not v[0] and v[1])}편")
    if started:
        log("새로 상영중:", ", ".join(started))
    if ended:
        log("상영중에서 빠짐:", ", ".join(ended))
    status.update(scrDate=last_day[5:], scrAt=now_iso(), scr=scr)
    save("status.json", status, depth=2)


if __name__ == "__main__":
    run(main)
