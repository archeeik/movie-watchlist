"""OTT: 왓챠(구독/구매, 왓챠 검색) + 넷플릭스(JustWatch) → data/status.json 의 ott, ottAt

    python scripts/ott.py          # 개봉 6개월 이내는 매번, 그 이전(재개봉·기획전 포함)은 격주(ISO 주 번호가 짝수인 주)
    python scripts/ott.py --all    # 전부 조회
    python scripts/ott.py --netflix-only   # 넷플릭스만(왓챠 값은 그대로) — GitHub Actions용
    python scripts/ott.py --watcha-only    # 왓챠만(넷플릭스 값은 그대로) — 국내 PC용

왓챠는 해외 IP를 HTTP 451로 막아서 GitHub Actions에서는 조회할 수 없다. 그래서 Actions는 넷플릭스만,
왓챠는 PC의 작업 스케줄러(scripts/watcha_local.py)가 맡는다.

동명 영화가 많아 감독·제작연도로 거른다. 걸러낸 것과 보조 판정은 로그에 남겨 사람이 확인할 수 있게 한다.
"""
import json
import re
import sys
import urllib.parse
from datetime import timedelta
from difflib import SequenceMatcher

from common import CollectError, fetch_json, load, log, now_iso, nz, run, save, today

WATCHA = "https://watcha.com/api/aio_searches/v2/search_2/all?query="
WATCHA_H = {"accept": "application/vnd.frograms+json;version=20", "x-frograms-client": "Galaxy-Web-App",
            "x-frograms-app-code": "Galaxy", "x-frograms-version": "2.1.0",
            "x-frograms-galaxy-language": "ko", "x-frograms-galaxy-region": "KR"}
JW = "https://apis.justwatch.com/graphql"
JW_Q = ('t%d: popularTitles(country:KR, first:3, filter:{searchQuery:%s, objectTypes:[MOVIE]}){edges{node{... on MovieOrShow{'
        'content(country:KR,language:"ko"){title originalReleaseYear} '
        'offers(country:KR,platform:WEB,filter:{packages:["nfx","nfa"]}){monetizationType}}}}}')
CHUNK = 30
RECENT_DAYS = 183   # 개봉 후 이 기간까지는 매주 조회, 그 뒤는 격주
RERELEASE = re.compile(r"\s*(디 오리지널|4K|리마스터링|리마스터|감독판|확장판|파이널 컷|재개봉)(\s|$)")


def same_title(a, b):
    a, b = nz(a), nz(b)
    return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))


def is_future(f, t):
    d = f.get("d", "")
    return bool(d) and (d + "-01" if len(d) == 7 else d) > t


def name_like(a, b):
    """감독 이름 표기 차이(하니아/하니야, 락세/라셰) 정도면 True."""
    return SequenceMatcher(None, nz(a), nz(b)).ratio() >= 0.45


def search_titles(f):
    """검색어 후보: 원래 제목(또는 q) → 재개봉 꼬리표를 뗀 제목"""
    q = f.get("q") or f["t"]
    short = RERELEASE.sub("", q).strip(" :-")
    return [q] + ([short] if short and short != q else [])


def watcha(f, old):
    """→ ({w, wid} 또는 {}, 로그 메모). old는 이전에 확인된 값."""
    movies, q = [], ""
    for q in search_titles(f):
        j = fetch_json(WATCHA + urllib.parse.quote(q), headers=WATCHA_H, pause=1.5)
        items = (j.get("result") or {}).get("items")
        if items is None:
            raise CollectError("왓챠 검색 응답에 result.items가 없음 — 구조가 바뀐 것 같음")
        movies = [it for it in items if it.get("cell_type") == "list_item_portrait"
                  and (it.get("subtitle") or "").startswith("영화") and same_title(it.get("title"), q)]
        if movies:
            break
    wid = lambda it: ((it.get("relations") or [{}])[0] or {}).get("id")
    dirs = [d.strip() for d in f.get("dir", "").split(",") if d.strip()]
    note = ""
    # 1) 이전에 확인된 콘텐츠 id와 같으면 인정  2) 감독 이름이 subtitle에 있으면 인정
    hit = next((it for it in movies if old.get("wid") and wid(it) == old["wid"]), None)         or next((it for it in movies if any(d in it["subtitle"] for d in dirs)), None)
    if not hit:
        for it in movies:   # 3) 감독 표기 차이 보조 판정: 제목 완전 일치 + 제작연도 ±1 + 감독 이름이 비슷함
            parts = [x.strip() for x in it["subtitle"].split("·")]
            yr = [int(x) for x in parts if x.isdigit() and len(x) == 4]
            who = parts[1] if len(parts) >= 3 else ""
            if nz(it.get("title")) == nz(q) and yr and abs(yr[-1] - f["y"]) <= 1 and any(name_like(d, who) for d in dirs):
                hit, note = it, f"보조 판정(감독 표기 다름): {f['t']} / 씨네21 감독 {f.get('dir')} / 왓챠 '{it['subtitle']}'"
                break
    if not hit:
        if old.get("w"):    # 검색에서 못 찾았다고 바로 지우지 않는다
            return {k: old[k] for k in ("w", "wid") if k in old}, f"확인 필요(이전 값 유지): {f['t']} — 왓챠 검색에서 같은 작품을 찾지 못함"
        if movies:
            note = f"동명 영화 제외: {f['t']} ({f.get('dir')}, {f['y']}) ≠ " + " | ".join(it["subtitle"] for it in movies[:3])
        return {}, note
    out = {"w": "b" if hit.get("badge") else "s"}
    if wid(hit):
        out["wid"] = wid(hit)
    return out, note


def netflix(films):
    """→ 넷플릭스에 있는 작품 id 집합"""
    found = set()
    for i in range(0, len(films), CHUNK):
        part = films[i:i + CHUNK]
        query = "query{" + " ".join(JW_Q % (f["id"], json.dumps(f.get("q") or f["t"], ensure_ascii=False)) for f in part) + "}"
        j = fetch_json(JW, data=json.dumps({"query": query}).encode(), headers={"content-type": "application/json"}, pause=1)
        data = j.get("data")
        if not data:
            raise CollectError(f"JustWatch 응답에 data가 없음: {str(j)[:200]}")
        for f in part:
            q = nz(f.get("q") or f["t"])
            for e in (data.get(f"t{f['id']}") or {}).get("edges", []):
                n = e.get("node") or {}
                c = n.get("content") or {}
                a = nz(c.get("title"))
                title_ok = same_title(a, q) or (len(q) >= 4 and q[:4] in a)
                year_ok = c.get("originalReleaseYear") and abs(c["originalReleaseYear"] - f["y"]) <= 1
                if n.get("offers") and year_ok and not title_ok:
                    log(f"넷플릭스 동명·유사작 제외: {f['t']} ({f['y']}) ≠ {c.get('title')} ({c.get('originalReleaseYear')})")
                if n.get("offers") and year_ok and title_ok:
                    found.add(f["id"])
                    break
    return found


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
    do_nfx, do_wat = "--watcha-only" not in sys.argv, "--netflix-only" not in sys.argv
    if "--limit" in sys.argv:   # 시험용: 앞의 N편만
        targets = targets[:int(sys.argv[sys.argv.index("--limit") + 1])]
    log(f"조회 대상 {len(targets)}편(개봉 6개월 이내 {sum(1 for f in released if recent(f))}편"
        + (f", 그 이전 {sum(1 for f in released if not recent(f))}편 포함)" if old_turn else ", 그 이전 작품은 이번 주 쉼)"))
    nfx = netflix(targets) if do_nfx else {f["id"] for f in targets if old.get(str(f["id"]), {}).get("n")}
    new, errors = {}, 0
    for f in targets:
        k = str(f["id"])
        try:
            if do_wat:
                w, note = watcha(f, old.get(k, {}))
            else:
                w, note = {x: old[k][x] for x in ("w", "wid") if x in old.get(k, {})}, ""
        except CollectError as e:
            errors += 1
            log(f"왓챠 조회 실패(이전 값 유지): {f['t']} — {e}")
            if errors > max(5, len(targets) // 10):
                raise CollectError("왓챠 조회 실패가 너무 많음 — 차단됐거나 구조가 바뀐 것 같음")
            w, note = {x: old[k][x] for x in ("w", "wid", "p") if x in old.get(k, {})}, ""
        if note:
            log(note)
        o = {}
        if f["id"] in nfx:
            o["n"] = "s"
        o.update(w)
        if o.get("w") == "b" and old.get(k, {}).get("p") and old[k].get("wid") == o.get("wid"):
            o["p"] = old[k]["p"]   # 단품 가격은 손으로 넣은 값을 보존
        if o:
            new[k] = o
    name = {str(f["id"]): f["t"] for f in films}
    for k in sorted(set(old) | set(new), key=int):
        a, b = old.get(k, {}), new.get(k, {})
        if k in name and k in {str(f["id"]) for f in targets} and {x: a.get(x) for x in "nw"} != {x: b.get(x) for x in "nw"}:
            log(f"OTT 변경: {name[k]} {a or '없음'} → {b or '없음'}")
    checked = {str(f["id"]) for f in targets}
    before = sum(1 for k in old if k in checked)
    if before >= 20 and len(new) < before * 0.5:
        raise CollectError(f"조회한 작품 중 OTT 제공작이 {before} → {len(new)}편으로 급감 — 저장하지 않음(구조 확인 필요)")
    for k, v in old.items():   # 이번에 조회하지 않은 작품(개봉 전, 격주 대상)은 그대로 둔다
        if k not in checked:
            new[k] = v
    status["ott"] = new
    if do_wat:
        status["ottAt"] = now_iso()        # 화면의 'OTT 확인' 날짜는 왓챠까지 확인한 때
    if do_nfx:
        status["nfxAt"] = now_iso()
    save("status.json", status, depth=2)
    log(f"저장: 넷플릭스 {sum(1 for v in new.values() if v.get('n'))}편, 왓챠 구독 {sum(1 for v in new.values() if v.get('w') == 's')}편, "
        f"구매 {sum(1 for v in new.values() if v.get('w') == 'b')}편")


if __name__ == "__main__":
    run(main)
