"""상영시간표: 오늘부터 공개된 날까지 → data/showtimes.json

네이버 플레이스의 영화관 페이지에 실려 있는 상영 일정을 읽는다(극장마다 하루 1회 요청).
디트릭스는 GitHub Actions 서버에서 응답하지 않고, CGV 사이트는 자동 접근을 차단해서 쓰지 않는다.
CGV 대학로는 오늘부터 약 4일치만 실린다.
"""
import json
import re

from common import CollectError, fetch_text, load, log, now_iso, run, save, today

NAVER = "https://pcmap.place.naver.com/theater/{}/movie"
THEATERS = {"cube": "13182210", "emu": "37842043", "ari": "11622504", "cgv": "12165843"}   # 네이버 장소 번호
HHMM = re.compile(r"^\d{2}:\d{2}$")


def screen(name):
    """'5관[CGV아트하우스] B1층' → '5관 아트하우스', '8관 4층 (컴포트석)' → '8관', '아리랑인디웨이브' → '3관'"""
    name = name.replace("(컴포트석)", "").replace("(Laser)", "").replace("[CGV아트하우스]", " 아트하우스")
    name = re.sub(r"\s*B?\d+층", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return "3관" if name.startswith("아리랑인디웨이브") else name


def theater_days(k, pid):
    """페이지에 내장된 데이터(__APOLLO_STATE__)의 movieTimes → {날짜: [[시작, 끝, 제목, 관]]}"""
    t = fetch_text(NAVER.format(pid), headers={"Accept-Language": "ko"}, pause=1.5)
    m = re.search(r"window\.__APOLLO_STATE__\s*=\s*", t)
    if not m:
        raise CollectError(f"{k}: 네이버 플레이스 페이지에서 내장 데이터를 찾지 못함 — 차단됐거나 구조가 바뀐 것 같음")
    state, _ = json.JSONDecoder().raw_decode(t, m.end())
    detail = next((v for key, v in state.get("ROOT_QUERY", {}).items() if key.startswith("placeDetail")), None)
    if not detail or not isinstance(detail.get("movieTimes"), list):
        raise CollectError(f"{k}: 네이버 플레이스 데이터에 movieTimes가 없음 — 구조가 바뀐 것 같음")
    out = {}
    for mv in detail["movieTimes"]:
        for sl in mv.get("scheduleList") or []:
            for s in sl.get("schedule") or []:
                a, b = s.get("rtime"), s.get("rendtime")
                if not (mv.get("date") and mv.get("name") and sl.get("theaterName") and a and b and HHMM.match(a) and HHMM.match(b)):
                    raise CollectError(f"{k}: 회차 형식이 예상과 다름: {mv.get('name')} {s}")
                if b < a:   # 자정을 넘기는 회차는 24시 이후로 표기
                    b = f"{int(b[:2]) + 24}:{b[3:]}"
                out.setdefault(mv["date"], []).append([a, b, mv["name"].strip(), screen(sl["theaterName"])])
    if not out:
        raise CollectError(f"{k}: 상영 일정이 하나도 없음 — 장소 번호나 구조 확인 필요")
    return {d: sorted(L) for d, L in out.items()}


def main():
    start = today().isoformat()
    old = load("showtimes.json", {})
    days, pub, errors = {}, {}, []
    # 극장 하나가 실패해도 나머지는 저장하고, 끝에서 실패로 알린다
    for k, pid in THEATERS.items():
        try:
            total = 0
            for d, L in theater_days(k, pid).items():
                if d < start:
                    continue
                total += len(L)
                days.setdefault(d, {})[k] = L
                if len(L) >= 3:
                    pub[k] = max(pub.get(k, ""), d)
            log(f"{k}: {total}회차, 공개 마지막 날 {pub.get(k, '-')}")
        except CollectError as e:
            errors.append(str(e))
            # 실패한 극장은 이전에 받아 둔 오늘 이후 시간표를 그대로 둔다
            for d, x in (old.get("days") or {}).items():
                if d >= start and x.get(k):
                    days.setdefault(d, {})[k] = x[k]
            if (old.get("pub") or {}).get(k):
                pub[k] = old["pub"][k]
    at = old.get("at") if len(errors) == len(THEATERS) and old.get("at") else now_iso()
    save("showtimes.json", {"at": at, "pub": pub, "days": {d: days[d] for d in sorted(days)}}, depth=2)
    log(f"저장: {len(days)}일")
    if errors:
        raise CollectError(" / ".join(errors))


if __name__ == "__main__":
    run(main)
