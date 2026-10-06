#!/usr/bin/env python3
"""Threads @jinggle_m daily auto post.

Runs on GitHub Actions (hourly between 10:00 and 22:00 KST).
- Posts at most ONE post per KST day, at a random time.
- Only publishes posts. Never follows, likes, comments, replies or reposts.
- Text: Gemini + Google Search (finds a current Korean meme/trend).
- Image: Gemini image model (new casual smartphone-style photo, no reused photos).
"""
import base64
import datetime
import glob
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
GRAPH = "https://graph.threads.net/v1.0"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"

TEXT_MODEL = os.environ.get("TEXT_MODEL") or "gemini-2.5-flash"
IMAGE_MODEL = os.environ.get("IMAGE_MODEL") or "gemini-3.1-flash-image"
FIRST_HOUR = int(os.environ.get("POST_FIRST_HOUR_KST") or 10)
LAST_HOUR = int(os.environ.get("POST_LAST_HOUR_KST") or 22)
EXPECTED_USERNAME = (os.environ.get("EXPECTED_USERNAME") or "jinggle_m").lower()
RUN_MODE = (os.environ.get("RUN_MODE") or "auto").strip().lower()  # auto | dry_run | force

POSTS_DIR = "posts"
OUT_DIR = "out"

BANNED = ["맞팔", "선팔", "스하리", "반하리", "#", "http", "www."]

PERSONA = """너는 Threads 계정 '징글'(@jinggle_m)의 글을 쓰는 사람이야.
계정 설정: 고양이 '규비'를 키우는 직장인. 연인 '밍글'과 같이 유튜브를 막 시작함.
말투: 친구한테 하듯 편한 반말. 'ㅋㅋㅋㅋ', '~했오', '~엉?' 같은 귀여운 말투를 가끔 섞음. 이모지는 0~1개.

이 계정의 예전 글 예시:
1) 다들 추셕은 잘 지냈엉?
우리 규비는 기절했오 ㅋㅋㅋㅋㅋ
2) 커플끼리 같이 유튜브 시작했는데 벌써부터 의견 안 맞음
나는 귀엽고 웃긴 거 하고 싶고 밍글이는 자꾸 뭔가 제대로 하고 싶어함
커플끼리 뭐 같이 하면 원래 이렇게 회의하다가 싸우는 거 맞지?
3) 이 시간에 이런 사진 보는 거 반칙 아님?ㅋㅋㅋㅋ
이 정도면 밥이 반찬인데
다들 스팸 얇게 여러 장이 좋아 두껍게 두 장이 좋아?
"""


def log(msg):
    print(msg, flush=True)


def http(method, url, data=None, headers=None, timeout=180):
    headers = dict(headers or {})
    body = None
    if data is not None:
        if headers.get("Content-Type") == "application/json":
            body = json.dumps(data).encode()
        else:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        # never print query strings (they may contain tokens)
        raise RuntimeError(f"HTTP {e.code} {method} {url.split('?')[0]}: {detail[:800]}") from None


# ---------------- Threads ----------------

def threads_get(path, token, **params):
    params["access_token"] = token
    return http("GET", f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}")


def threads_post(path, token, **params):
    params["access_token"] = token
    return http("POST", f"{GRAPH}/{path}", data=params)


def threads_me(token):
    me = threads_get("me", token, fields="id,username")
    if (me.get("username") or "").lower() != EXPECTED_USERNAME:
        raise RuntimeError(f"토큰 계정이 @{EXPECTED_USERNAME} 이 아님: @{me.get('username')}")
    return me["id"]


def posted_today(user_id, token, today):
    data = threads_get(f"{user_id}/threads", token, fields="id,timestamp,media_type", limit=10)
    for item in data.get("data", []):
        if item.get("media_type") == "REPOST_FACADE":
            continue  # 리포스트는 내 글로 치지 않음
        ts = item.get("timestamp")
        if not ts:
            continue
        dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone(KST)
        if dt.date() == today:
            return True
    return False


def publish(user_id, token, text, image_url):
    c = threads_post(f"{user_id}/threads", token, media_type="IMAGE", image_url=image_url, text=text)
    cid = c["id"]
    for _ in range(36):
        time.sleep(5)
        st = threads_get(cid, token, fields="status,error_message")
        if st.get("status") == "FINISHED":
            break
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Threads 컨테이너 오류: {st}")
    else:
        raise RuntimeError("Threads 컨테이너가 3분 안에 준비되지 않음")
    p = threads_post(f"{user_id}/threads_publish", token, creation_id=cid)
    mid = p["id"]
    info = threads_get(mid, token, fields="permalink,timestamp")
    return mid, info.get("permalink")


# ---------------- Gemini ----------------

def gemini(model, body, key):
    return http(
        "POST",
        f"{GEMINI}/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )


def parse_json(text):
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("JSON 없음: " + text[:300])
    return json.loads(text[s : e + 1])


def recent_posts(n=14):
    items = []
    for path in sorted(glob.glob(f"{POSTS_DIR}/*.json"))[-n:]:
        try:
            with open(path, encoding="utf-8") as f:
                items.append(json.load(f))
        except Exception:
            pass
    return items


def write_post(today, key):
    history = recent_posts()
    hist_txt = "\n".join(f"- [{p.get('trend','')}] {p.get('text','')[:80]}" for p in history) or "(없음)"
    prompt = f"""{PERSONA}
최근에 이미 쓴 글 (같은 밈, 같은 소재 반복 금지):
{hist_txt}

할 일:
1. Google 검색으로 오늘({today.isoformat()}, 한국) 기준 최근 1~2주 사이 한국 SNS(스레드, 인스타, X, 숏폼)에서 유행하는 밈, 짤, 유행어, 챌린지를 찾아.
2. 그중 일상 이야기와 자연스럽게 엮을 수 있는 가볍고 무해한 것 하나를 골라.
3. 그 밈을 자연스럽게 녹인 일상 공감 글을 써.

규칙:
- 공백 포함 80~250자. 줄바꿈으로 읽기 편하게.
- 마지막에 사람들이 답하고 싶어지는 가벼운 질문 하나.
- 정치, 종교, 사건사고, 혐오, 실존 인물 비하, 광고, 해시태그, 링크 금지.
- 가게 이름, 정확한 장소, 숫자 같은 검증 가능한 사실 주장 금지.
- '맞팔', '선팔', '스하리', '반하리' 같은 팔로우 유도 문구 금지.
- 사진은 직접 폰으로 찍은 것 같은 평범한 일상 사진 1장. 고양이 규비가 나와도 좋음.
  사진 속에 글자, 로고, 브랜드, 만화 캐릭터, 사람 얼굴이 나오면 안 됨. 밈 원본 이미지를 따라 그리지 말 것.

출력은 아래 JSON 하나만:
{{"trend": "고른 밈 이름", "trend_reason": "요즘 유행이라는 근거 한 줄", "text": "게시글 본문", "image_prompt": "English description of the photo"}}
"""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 1.0},
    }
    last_err = None
    for attempt in range(3):
        try:
            r = gemini(TEXT_MODEL, body, key)
            parts = r["candidates"][0]["content"]["parts"]
            data = parse_json("".join(p.get("text", "") for p in parts))
            text = (data.get("text") or "").strip()
            if not text or len(text) > 400:
                raise ValueError(f"본문 길이 이상: {len(text)}")
            if any(b in text for b in BANNED):
                raise ValueError("금지 문구 포함")
            if not data.get("image_prompt"):
                raise ValueError("image_prompt 없음")
            data["text"] = text
            return data
        except Exception as e:  # retry
            last_err = e
            log(f"글 생성 재시도 {attempt + 1}: {e}")
    raise RuntimeError(f"글 생성 실패: {last_err}")


def make_image(image_prompt, key):
    prompt = (
        image_prompt.strip()
        + "\n\nStyle: an ordinary, slightly imperfect handheld smartphone photo taken by a regular person "
        "in Korea, natural indoor or outdoor light, casual framing, realistic textures and proportions, "
        "natural colors, not a studio or advertising shot. "
        "Strictly no text, letters, captions, logos, brands, watermarks, cartoon characters, "
        "or recognizable human faces. Portrait 4:5."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": "4:5"}},
    }
    r = gemini(IMAGE_MODEL, body, key)
    for p in r.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        d = p.get("inlineData") or p.get("inline_data")
        if d and d.get("data"):
            mime = d.get("mimeType") or d.get("mime_type") or "image/png"
            return base64.b64decode(d["data"]), ("jpg" if "jpeg" in mime else "png")
    raise RuntimeError("이미지가 생성되지 않음: " + json.dumps(r, ensure_ascii=False)[:500])


# ---------------- git helpers ----------------

def git(*args):
    subprocess.run(["git", *args], check=True)


def commit_push(paths, msg):
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", *paths)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
        git("commit", "-m", msg)
        for _ in range(3):
            if subprocess.run(["git", "push"]).returncode == 0:
                break
            git("pull", "--rebase")
        else:
            raise RuntimeError("git push 실패")
    return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()


def wait_url(url):
    for _ in range(24):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError("이미지 공개 주소에 접근할 수 없음")


def summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


# ---------------- main ----------------

def should_post_now(now):
    if RUN_MODE in ("force", "dry_run"):
        return True
    if now.hour < FIRST_HOUR:
        return False
    if now.hour >= LAST_HOUR:
        return True  # 마지막 기회
    remaining = LAST_HOUR - now.hour + 1  # 남은 실행 횟수(이번 포함)
    return random.random() < 1.0 / remaining


def main():
    now = datetime.datetime.now(KST)
    today = now.date()
    log(f"KST {now:%Y-%m-%d %H:%M}, mode={RUN_MODE}")

    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or (RUN_MODE != "dry_run" and not token):
        log("아직 시크릿(THREADS_ACCESS_TOKEN / GEMINI_API_KEY) 설정 전이라 건너뜀")
        summary(["설정 대기 중: 시크릿이 아직 없음"])
        return

    if not should_post_now(now):
        log("이번 시간은 건너뜀 (오늘 게시 시간은 무작위로 정해짐)")
        return

    user_id = None
    if RUN_MODE != "dry_run":
        user_id = threads_me(token)
        if posted_today(user_id, token, today):
            log("오늘 이미 게시물이 있어 건너뜀 (하루 1개)")
            summary(["오늘 이미 게시됨, 건너뜀"])
            return

    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    meta_path = f"{POSTS_DIR}/{today.isoformat()}.json"

    draft = None
    if RUN_MODE != "dry_run" and os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            draft = json.load(f)
        if draft.get("published"):
            log("오늘 글은 이미 게시 기록이 있음")
            return
        log("오늘 만들어 둔 초안 재사용")

    if draft is None:
        data = write_post(today, key)
        log(f"밈: {data.get('trend')} / {data.get('trend_reason')}")
        img, ext = make_image(data["image_prompt"], key)
        draft = {
            "date": today.isoformat(),
            "trend": data.get("trend"),
            "trend_reason": data.get("trend_reason"),
            "text": data["text"],
            "image_prompt": data["image_prompt"],
            "image": f"{POSTS_DIR}/{today.isoformat()}.{ext}",
            "published": False,
        }
        with open(f"{OUT_DIR}/image.{ext}", "wb") as f:
            f.write(img)
        with open(f"{OUT_DIR}/post.json", "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
        if RUN_MODE == "dry_run":
            log("테스트 모드: 게시하지 않음. 결과는 Artifacts의 output 에서 확인")
            summary(["## 테스트 결과 (게시 안 함)", f"- 밈: {draft['trend']}", "", draft["text"]])
            return
        with open(draft["image"], "wb") as f:
            f.write(img)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)

    sha = commit_push([draft["image"], meta_path], f"draft {today.isoformat()}")
    repo = os.environ["GITHUB_REPOSITORY"]
    image_url = f"https://raw.githubusercontent.com/{repo}/{sha}/{draft['image']}"
    wait_url(image_url)

    # 게시 직전 한 번 더 확인 (하루 1개)
    if posted_today(user_id, token, today):
        log("게시 직전 확인: 오늘 이미 게시물이 있어 중단")
        return

    mid, permalink = publish(user_id, token, draft["text"], image_url)
    draft.update({"published": True, "media_id": mid, "permalink": permalink,
                  "published_at": datetime.datetime.now(KST).isoformat()})
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    commit_push([meta_path], f"posted {today.isoformat()}")
    log(f"게시 완료: {permalink}")
    summary(["## 게시 완료", f"- 링크: {permalink}", f"- 밈: {draft['trend']}", "", draft["text"]])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"오류: {e}")
        sys.exit(1)
