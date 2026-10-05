"""PC(국내 IP)에서 왓챠만 조회해 올린다. Windows 작업 스케줄러가 매주 실행한다.

왓챠는 해외 IP를 막아서 GitHub Actions에서는 조회할 수 없다.
순서: 최신 데이터 받기 → ott.py --watcha-only → status.json이 바뀌었으면 커밋·푸시(푸시하면 배포가 돈다).
기록은 logs/watcha_local.log. 실패하면 저장소에 '수집 실패' 이슈를 남긴다(GitHub CLI가 있을 때).

    pythonw scripts/watcha_local.py            # 창 없이 실행
    python scripts/watcha_local.py --limit 5   # 시험용: 앞의 5편만
"""
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "watcha_local.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PYTHON = Path(sys.executable).with_name("python.exe") if Path(sys.executable).name.lower() == "pythonw.exe" else Path(sys.executable)
GH = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"


def note(msg):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def sh(*cmd, check=True):
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    out = (r.stdout + r.stderr).strip()
    if out:
        note(f"$ {' '.join(Path(str(c)).name if i == 0 else str(c) for i, c in enumerate(cmd))}\n{out}")
    if check and r.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} {' '.join(str(c) for c in cmd[1:3])} 실패(종료 코드 {r.returncode}): {out[-300:]}")
    return r


def report(err):
    """GitHub Actions의 실패 알림과 같은 '수집 실패' 이슈에 남긴다."""
    body = f"PC에서 돌린 왓챠 수집 실패\n\n{err}"
    try:
        n = sh(GH, "issue", "list", "--state", "open", "--search", "수집 실패 in:title", "--json", "number", "--jq", ".[0].number", check=False).stdout.strip()
        if n:
            sh(GH, "issue", "comment", n, "--body", body, check=False)
        else:
            sh(GH, "issue", "create", "--title", "수집 실패", "--body", body, check=False)
    except Exception as e:   # gh가 없거나 로그인이 풀린 경우
        note(f"이슈를 남기지 못함: {e!r}")


def main():
    note("=== 시작 ===")
    try:
        sh("git", "pull", "--rebase", "--autostash")
        sh(PYTHON, "scripts/ott.py", "--watcha-only", *sys.argv[1:])
        sh("git", "add", "data/status.json")
        if sh("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
            note("바뀐 데이터 없음")
        else:
            sh("git", "commit", "-m", "데이터 갱신: 왓챠(PC)")
            sh("git", "pull", "--rebase", "--autostash")
            sh("git", "push")
        note("=== 끝(성공) ===")
    except Exception as e:
        note(f"=== 실패: {e} ===")
        report(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
