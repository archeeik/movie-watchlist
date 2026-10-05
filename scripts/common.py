"""수집 스크립트 공통 도구. 표준 라이브러리 + lxml만 쓴다."""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


class CollectError(Exception):
    """사이트 구조가 바뀌었거나 응답이 이상할 때. 스크립트를 실패로 끝내 알림이 가게 한다."""


def now():
    return datetime.now(KST)


def now_iso():
    return now().replace(microsecond=0).isoformat()


def today():
    return now().date()


def log(*a):
    print(*a, flush=True)


def fetch(url, *, headers=None, data=None, opener=None, retries=2, pause=0.4, ok=(200, 201)):
    """GET(또는 data가 있으면 POST). 실패하면 잠깐 쉬고 다시 시도, 끝내 안 되면 CollectError."""
    h = {"User-Agent": UA, **(headers or {})}
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with (opener.open if opener else urllib.request.urlopen)(req, timeout=30) as r:
                body = r.read()
                if r.status not in ok:
                    raise CollectError(f"HTTP {r.status}")
            time.sleep(pause)   # 저빈도 유지
            return body
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (401, 403, 404):
                break           # 차단·없음은 다시 시도하지 않는다
            if e.code == 429:   # 속도 제한: 길게 쉰다
                time.sleep(30 * (i + 1))
        except Exception as e:  # 시간 초과, 연결 오류 등
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise CollectError(f"{url.split('?')[0]} 조회 실패: {last}")


def fetch_text(url, **kw):
    return fetch(url, **kw).decode("utf-8", "replace")


def fetch_json(url, **kw):
    body = fetch(url, **kw)
    try:
        return json.loads(body)
    except ValueError:
        raise CollectError(f"{url.split('?')[0]} 응답이 JSON이 아님: {body[:120]!r}")


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(o, depth):
    """위에서 depth단계까지만 줄을 나누고 그 아래는 한 줄로 쓴다(커밋 변경 내역이 읽히게)."""
    if depth > 0 and isinstance(o, dict) and o:
        return "{\n" + ",\n".join(json.dumps(str(k), ensure_ascii=False) + ":" + _dump(v, depth - 1) for k, v in o.items()) + "\n}"
    if depth > 0 and isinstance(o, list) and o:
        return "[\n" + ",\n".join(_dump(v, depth - 1) for v in o) + "\n]"
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def save(name, obj, depth=1):
    # 줄 끝은 항상 LF — Windows에서 돌려도 GitHub에서 만든 파일과 줄 단위로 같게
    (DATA / name).write_text(_dump(obj, depth) + "\n", encoding="utf-8", newline="\n")


def nz(s):
    """제목 비교용 정규화: 공백·문장부호 제거, 소문자."""
    return re.sub(r"[\s:,.?!·\-&()'\"‘’“”~/\[\]<>]", "", s or "").lower()


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def run(main):
    """스크립트 진입점. CollectError면 메시지를 남기고 종료 코드 1."""
    try:
        main()
    except CollectError as e:
        log(f"::error::{e}")
        sys.exit(1)
