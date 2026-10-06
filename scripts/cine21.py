"""씨네21 전문가 별점: 별점 갱신 + 최근 개봉·6.00 이상 새 작품 추가 → data/films.json

    python scripts/cine21.py              # 별점 목록 앞 10쪽(매달 첫 실행은 45쪽 전체) + 새 작품·포스터 없는 최근작 상세
    python scripts/cine21.py --full       # 45쪽 전체
    python scripts/cine21.py --reviews-only   # 목록은 훑지 않고 한줄평 대상 작품의 전문가 한줄평만 다시 받기
    python scripts/cine21.py --range 2025-10-01 2025-12-31   # 지난 기간 보충: 그 기간 개봉작(6.00 이상)을 추가
    python scripts/cine21.py --range 2025-07-01 2025-09-30 --pages 65   # 45쪽 너머에 있는 더 오래된 기간
    python scripts/cine21.py --posters    # 포스터 주소(p)가 없는 모든 작품의 상세도 조회(최초 1회용)

별점 갱신은 개봉일이 최근 두 달 이내인 작품만 한다(그 뒤로는 별점이 바뀌지 않음).
있던 작품은 지우지 않는다(6.00 미만으로 떨어져도 별점만 고치고 로그에 남김).
"""
import re
import sys
import urllib.parse
from datetime import date, timedelta

from lxml import html

from common import CollectError, fetch_text, load, log, run, save, today, ws

BASE = "https://cine21.com"
PAGES = 10                   # 평소: 최신 리뷰순 앞쪽만(새 작품은 앞에 나온다)
PAGES_FULL = 45              # 매달 첫 실행(1~7일)과 --full: 뒤쪽에 섞여 나온 작품까지
NEW_DAYS = 183               # 새 작품으로 받는 범위: 개봉일이 최근 6개월 이내이거나 개봉 예정
MIN_SCORE = 6.0
UPDATE_DAYS = 62             # 별점 갱신 대상: 개봉일이 최근 두 달 이내(개봉 예정 포함)
POSTER_SIZE = "[X104,150]"   # 화면 52×75의 2배
REVIEW_QUARTERS = {"2026-4"}  # 전문가 한줄평을 받아 두는 분기(개봉 연도-분기) → data/reviews.json


def list_page(order, p):
    t = fetch_text(BASE + "/movie/point/list_items", data=urllib.parse.urlencode({"order": order, "p": p}).encode(),
                   headers={"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/movie/point"}, pause=0.5)
    out = []
    for a in html.fromstring(t or "<div/>").xpath('//a[contains(@href,"movie_id=")]'):
        m = re.search(r"movie_id=(\d+)", a.get("href"))
        title = ws("".join(a.xpath('.//p[contains(@class,"title")]//text()')))
        score = None
        for w in a.xpath('.//div[contains(@class,"star_wrap")]'):
            if "전문가" in w.text_content():
                num = ws("".join(w.xpath('.//p[contains(@class,"num")]//text()')))
                score = float(num) if re.fullmatch(r"\d+(\.\d+)?", num) else None
        d = re.search(r"개봉일\s*:\s*(\d{4}-\d{2}(?:-\d{2})?)", a.text_content())
        if m and title:
            out.append({"id": int(m.group(1)), "t": title, "s": score, "d": d.group(1) if d else ""})
    return out


def scan(pages):
    page = html.fromstring(fetch_text(BASE + "/movie/point"))
    order = page.xpath('//select[@id="point_list_order"]/option[1]/@value')
    if not order:
        raise CollectError("씨네21 별점 페이지에서 정렬 값(#point_list_order)을 찾지 못함")
    seen = {}
    for p in range(1, pages + 1):
        items = list_page(order[0], p)
        if not items:
            if p <= 5:
                raise CollectError(f"씨네21 별점 목록 {p}쪽이 비어 있음 — 구조가 바뀐 것 같음")
            break
        for it in items:
            seen.setdefault(it["id"], {**it, "page": p})
    if len(seen) < pages * 5 or sum(1 for v in seen.values() if v["s"] is not None) < len(seen) * 0.5:
        raise CollectError(f"씨네21 별점 목록을 제대로 읽지 못함({len(seen)}편)")
    return seen


def detail(mid):
    """상세 페이지 → {d, c, dir, cast, min, y, p} 중 읽힌 것만."""
    doc = html.fromstring(fetch_text(f"{BASE}/movie/info/?movie_id={mid}", pause=0.5))
    out = {}
    for li in doc.xpath('//*[contains(@class,"info_list")]//li'):
        key = ws("".join(li.xpath('./p[contains(@class,"title")]//text()')))
        names = [ws(a.text_content()) for a in li.xpath(".//a")]
        val = ws(li.text_content())[len(key):].strip()
        if key == "개봉" and re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", val):
            out["d"] = val
        elif key == "국가":
            out["c"] = ", ".join(names) if names else val
        elif key == "감독":
            out["dir"] = ", ".join(names) if names else val
        elif key == "출연":
            out["cast"] = ", ".join((names or val.split())[:3])
        elif key == "시간":
            m = re.search(r"(\d+)\s*분", val)
            if m:
                out["min"] = int(m.group(1))
    eng = ws(" ".join(doc.xpath('//*[contains(@class,"movie_title")]//*[contains(@class,"eng")]//text()')))
    m = re.search(r"\((\d{4})\)", eng)
    if m:
        out["y"] = int(m.group(1))
    src = doc.xpath('//*[contains(@class,"movie_detail_info")]//*[contains(@class,"poster")]//img/@src')
    if src and "/poster/" in src[0] and "noimg" not in src[0]:
        out["p"] = re.sub(r"\[[^\]]*\]", POSTER_SIZE, src[0], count=1)
    # 전문가 별점 목록: [평론가, 별점, 한줄평]
    out["rv"] = []
    for li in doc.xpath('//section[contains(@class,"expert_star")]//ul[contains(@class,"expert_star_list")]/li'):
        name = ws("".join(li.xpath('.//p[contains(@class,"name")]//text()')))
        num = ws("".join(li.xpath('.//p[contains(@class,"num")]//text()')))
        text = ws("".join(li.xpath('.//div[contains(@class,"review")][not(contains(@class,"reviewer"))]//text()')))
        if name and re.fullmatch(r"\d+(\.\d+)?", num):
            out["rv"].append([name, float(num) if "." in num else int(num), text])
    return out


def review_target(f):
    """한줄평을 받아 두는 작품인가(REVIEW_QUARTERS에 든 분기의 개봉작)"""
    d = f.get("d", "")
    return len(d) >= 7 and f"{d[:4]}-{(int(d[5:7]) + 2) // 3}" in REVIEW_QUARTERS


def main():
    all_posters = "--posters" in sys.argv
    films = load("films.json")
    by_id = {f["id"]: f for f in films}
    reviews = load("reviews.json", {})
    if "--reviews-only" in sys.argv:
        for f in films:
            if review_target(f):
                reviews[str(f["id"])] = detail(f["id"])["rv"]
                log(f"한줄평: {f['t']} {len(reviews[str(f['id'])])}명")
        save("reviews.json", {k: v for k, v in sorted(reviews.items(), key=lambda kv: int(kv[0])) if v}, depth=1)
        return
    since = (today() - timedelta(days=NEW_DAYS)).isoformat()
    is_new = lambda d: (d + "-31")[:10] >= since   # 연도가 바뀌어도 이어지게 '올해'가 아니라 기간으로 본다
    full = "--full" in sys.argv or today().day <= 7
    if "--range" in sys.argv:   # 지난 기간 보충: 새 작품 기준을 그 기간으로 바꾸고 전체를 훑는다
        lo, hi = sys.argv[sys.argv.index("--range") + 1:][:2]
        is_new = lambda d: lo <= (d + "-15")[:10] <= hi
        full = True
        log(f"기간 보충: {lo} ~ {hi}")
    pages = PAGES_FULL if full else PAGES
    if "--pages" in sys.argv:   # 45쪽 너머(더 오래된 개봉작)까지 훑을 때
        pages = int(sys.argv[sys.argv.index("--pages") + 1])
    seen = scan(pages)
    log(f"별점 목록 {len(seen)}편 확인(앞 {pages}쪽)")

    # 1) 있던 작품: 별점만 갱신. 개봉 후 두 달이 지나면 별점이 더 바뀌지 않으므로 그대로 둔다(재개봉·기획전 그룹 포함)
    cutoff = (today() - timedelta(days=UPDATE_DAYS)).isoformat()
    fresh = lambda f: bool(f.get("d")) and (f["d"] + "-31")[:10] >= cutoff
    for mid, it in seen.items():
        f = by_id.get(mid)
        if f and fresh(f) and it["s"] is not None and abs(it["s"] - f["s"]) > 1e-9:
            log(f"별점 변경: {f['t']} {f['s']:.2f} → {it['s']:.2f}" + ("  ※ 6.00 미만(삭제하지 않음)" if it["s"] < MIN_SCORE else ""))
            f["s"] = it["s"]

    # 2) 새 작품: 6.00 이상이고 최근 6개월 안에 개봉했거나 개봉 예정(목록에 개봉일이 없으면 상세에서 확인)
    # 목록에 개봉일이 없는 후보는 상세를 확인한 날을 기억해 둔다(최근 리뷰 5쪽 안이면 6일, 그 밖은 60일 뒤 재확인)
    checked = load("cine21_checked.json", {})
    added = []
    for mid, it in seen.items():
        if mid in by_id or it["s"] is None or it["s"] < MIN_SCORE:
            continue
        if it["d"] and not is_new(it["d"]):
            continue
        if not it["d"]:
            last = checked.get(str(mid))
            wait = 6 if it["page"] <= 5 else 60
            if last and (today() - date.fromisoformat(last)).days < wait:
                continue
        info = detail(mid)
        d = info.get("d") or it["d"]
        if not d or not is_new(d):
            if not it["d"]:
                checked[str(mid)] = today().isoformat()
            continue
        checked.pop(str(mid), None)
        if not info.get("dir") or not info.get("y"):
            raise CollectError(f"씨네21 상세({mid} {it['t']})에서 감독·제작연도를 읽지 못함 — 구조 확인 필요")
        f = {"id": mid, "min": info.get("min"), "t": it["t"], "s": it["s"], "d": d, "c": info.get("c", ""),
             "dir": info["dir"], "cast": info.get("cast", ""), "y": info["y"]}
        if info["y"] <= 2015:
            f["rr"] = f"{info['y']}년작 재개봉"
        if info.get("p"):
            f["p"] = info["p"]
        f = {k: v for k, v in f.items() if v not in (None, "")}
        films.insert(0, f)
        by_id[mid] = f
        added.append(f)
        if review_target(f):
            reviews[str(mid)] = info["rv"]
        log(f"새 작품: {f['t']} ({mid}) ★{f['s']:.2f} 개봉 {d} 감독 {f['dir']}")

    # 3) 포스터 주소가 없는 작품(최근·개봉 예정작만, --posters면 전부) + 개봉일이 월까지만 있는 작품
    recent = (today() - timedelta(days=30)).isoformat()
    for f in films:
        if f in added:
            continue
        month_only = len(f.get("d", "")) == 7
        need_poster = not f.get("p") and (all_posters or (not f.get("re") and f.get("d", "") >= recent))
        need_reviews = review_target(f) and fresh(f)   # 별점이 아직 바뀔 수 있는 동안(개봉 두 달 이내)만 다시 받는다
        if not (need_poster or month_only or need_reviews):
            continue
        info = detail(f["id"])
        if need_reviews:
            reviews[str(f["id"])] = info["rv"]
        if info.get("p") and not f.get("p"):
            f["p"] = info["p"]
        if month_only and len(info.get("d", "")) == 10:
            log(f"개봉일 확정: {f['t']} {f['d']} → {info['d']}")
            f["d"] = info["d"]

    save("films.json", films, depth=1)
    save("reviews.json", {k: v for k, v in sorted(reviews.items(), key=lambda kv: int(kv[0])) if v}, depth=1)
    save("cine21_checked.json", dict(sorted(checked.items(), key=lambda kv: int(kv[0]))), depth=1)
    if added:
        log("새 작품 id: " + ",".join(str(f["id"]) for f in added))
    log(f"저장: {len(films)}편(새 작품 {len(added)}편, 포스터 주소 없는 작품 {sum(1 for f in films if not f.get('p'))}편)")


if __name__ == "__main__":
    run(main)
