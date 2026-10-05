"""상영시간표: 오늘부터 공개된 날까지 → data/showtimes.json

디트릭스: 씨네큐브 광화문·에무시네마·아리랑시네센터(21일치).
CGV 대학로: CGV 사이트는 자동 접근을 차단하므로(403 '비정상 접속') 네이버 플레이스의 영화관 페이지에
실려 있는 상영 일정을 읽는다(하루 1회 요청, 오늘부터 약 4일치).
"""
import json
import re
from datetime import timedelta

from common import CollectError, fetch_json, fetch_text, load, log, now_iso, run, save, today

DTRYX = "https://www.dtryx.com/cinema/showseq_list.do?cgid=FE8EF4D2-F22D-4802-A39A-D58F23A29C1E&ssid=&tokn=&BrandCd={b}&CinemaCd={c}&PlaySDT={d}"
THEATERS = {"cube": ("indieart", "000003"), "emu": ("indieart", "000069"), "ari": ("etc", "000088")}
NAVER_CGV = "https://pcmap.place.naver.com/theater/12165843/movie"   # CGV 대학로
DAYS = 21
HHMM = re.compile(r"^\d{2}:\d{2}$")


def screen(name):
    name = name.replace("(Laser)", "").strip()
    return "3관" if name == "아리랑인디웨이브관" else name


def day_list(brand, cinema, d):
    j = fetch_json(DTRYX.format(b=brand, c=cinema, d=d), headers={"X-Requested-With": "XMLHttpRequest"}, pause=0.25)
    if "Showseqlist" not in j:
        raise CollectError(f"디트릭스 응답에 Showseqlist가 없음({cinema} {d}) — 구조가 바뀐 것 같음")
    out = []
    for s in j["Showseqlist"] or []:
        a, b, t, sc = s.get("StartTime"), s.get("EndTime"), s.get("MovieNm"), s.get("ScreenNm")
        if not (a and b and t and sc and HHMM.match(a) and HHMM.match(b)):
            raise CollectError(f"디트릭스 회차 형식이 예상과 다름({cinema} {d}): {s}")
        if b < a:   # 자정을 넘기는 회차는 24시 이후로 표기
            b = f"{int(b[:2]) + 24}:{b[3:]}"
        out.append([a, b, t.strip(), screen(sc)])
    return sorted(out)


def cgv_screen(name):
    """'5관[CGV아트하우스] B1층' → '5관 아트하우스', '8관 4층 (컴포트석)' → '8관'"""
    name = name.replace("(컴포트석)", "").replace("[CGV아트하우스]", " 아트하우스")
    name = re.sub(r"\s*B?\d+층", "", name)
    return re.sub(r"\s+", " ", name).strip()


def cgv_days():
    """네이버 플레이스 페이지에 내장된 데이터(__APOLLO_STATE__)의 movieTimes → {날짜: [[시작, 끝, 제목, 관]]}"""
    t = fetch_text(NAVER_CGV, headers={"Accept-Language": "ko"})
    m = re.search(r"window\.__APOLLO_STATE__\s*=\s*", t)
    if not m:
        raise CollectError("네이버 플레이스(CGV 대학로) 페이지에서 내장 데이터를 찾지 못함 — 차단됐거나 구조가 바뀐 것 같음")
    state, _ = json.JSONDecoder().raw_decode(t, m.end())
    detail = next((v for k, v in state.get("ROOT_QUERY", {}).items() if k.startswith("placeDetail")), None)
    if not detail or not isinstance(detail.get("movieTimes"), list):
        raise CollectError("네이버 플레이스(CGV 대학로) 데이터에 movieTimes가 없음 — 구조가 바뀐 것 같음")
    out = {}
    for mv in detail["movieTimes"]:
        for sl in mv.get("scheduleList") or []:
            for s in sl.get("schedule") or []:
                a, b = s.get("rtime"), s.get("rendtime")
                if not (mv.get("date") and mv.get("name") and sl.get("theaterName") and a and b and HHMM.match(a) and HHMM.match(b)):
                    raise CollectError(f"네이버 플레이스(CGV 대학로) 회차 형식이 예상과 다름: {mv.get('name')} {s}")
                out.setdefault(mv["date"], []).append([a, b, mv["name"].strip(), cgv_screen(sl["theaterName"])])
    if not out:
        raise CollectError("네이버 플레이스(CGV 대학로)에 상영 일정이 하나도 없음 — 구조 확인 필요")
    return {d: sorted(L) for d, L in out.items()}


def main():
    start = today()
    dates = [(start + timedelta(days=i)).isoformat() for i in range(DAYS)]
    old = load("showtimes.json", {})
    days, pub, errors = {}, {}, []

    def keep_old(k):
        """조회에 실패한 극장은 이전에 받아 둔 오늘 이후 시간표를 그대로 둔다."""
        for d, x in (old.get("days") or {}).items():
            if d >= dates[0] and x.get(k):
                days.setdefault(d, {})[k] = x[k]
        if (old.get("pub") or {}).get(k):
            pub[k] = old["pub"][k]

    # 극장 하나가 실패해도 나머지는 저장하고, 끝에서 실패로 알린다
    for k, (b, c) in THEATERS.items():
        try:
            got, last, total = {}, None, 0
            for d in dates:
                L = day_list(b, c, d)
                total += len(L)
                if L:
                    got[d] = L
                if len(L) >= 3:
                    last = d
            if total == 0:
                raise CollectError(f"{k}: {DAYS}일 동안 회차가 하나도 없음 — 극장 코드나 응답 구조 확인 필요")
            for d, L in got.items():
                days.setdefault(d, {})[k] = L
            if last:
                pub[k] = last
            log(f"{k}: {total}회차, 공개 마지막 날 {last or '-'}")
        except CollectError as e:
            errors.append(f"{k}: {e}")
            keep_old(k)
    try:
        total = 0
        for d, L in cgv_days().items():
            if d < dates[0]:
                continue
            total += len(L)
            days.setdefault(d, {})["cgv"] = L
            if len(L) >= 3:
                pub["cgv"] = max(pub.get("cgv", ""), d)
        log(f"cgv: {total}회차, 공개 마지막 날 {pub.get('cgv', '-')}")
    except CollectError as e:
        errors.append(f"cgv: {e}")
        keep_old("cgv")

    out = {"at": old.get("at") if len(errors) == len(THEATERS) + 1 else now_iso(), "pub": pub, "days": {d: days[d] for d in sorted(days)}}
    save("showtimes.json", out, depth=2)
    log(f"저장: {len(days)}일")
    if errors:
        raise CollectError(" / ".join(errors))


if __name__ == "__main__":
    run(main)
