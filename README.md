# threads-daily-post

Threads **@jinggle_m** 자동 게시 봇. 컴퓨터가 꺼져 있어도 GitHub 서버에서 실행돼요.

## 하는 일

- 매일 10시~22시(한국 시간) 사이 무작위 시간에 **하루 1개**만 게시
- Gemini 무료 등급 + Google 검색으로 요즘 유행하는 밈을 찾아 일상 글 작성
- Cloudflare Workers AI 무료 할당량(FLUX.1 schnell)으로 폰으로 찍은 듯한 새 사진 생성 (남의 사진, 짤 원본은 사용 안 함)
- 전부 무료 범위 안에서 동작 (결제 등록 불필요)
- 그날 이미 게시물이 있으면 (직접 올린 글 포함) 건너뜀
- **팔로우, 좋아요, 댓글, 답글, 리포스트는 절대 하지 않음** (게시만 함)

## 필요한 시크릿 (Settings > Secrets and variables > Actions)

| 이름 | 내용 |
| --- | --- |
| `THREADS_ACCESS_TOKEN` | Threads API 장기 액세스 토큰 (`threads_basic`, `threads_content_publish`) |
| `GEMINI_API_KEY` | Google AI Studio API 키 (무료 등급, 글 생성용) |
| `CF_ACCOUNT_ID` | Cloudflare 계정 ID (이미지 생성용) |
| `CF_API_TOKEN` | Cloudflare API 토큰 (Workers AI 권한) |
| `GH_PAT` | 이 저장소의 Secrets 쓰기 권한이 있는 Fine-grained 토큰 (Threads 토큰 자동 연장용) |

선택 변수 (Variables): `TEXT_MODEL` (기본 `gemini-2.5-flash`), `IMAGE_MODEL` (기본 `@cf/black-forest-labs/flux-1-schnell`)

## 사용법

- **테스트:** Actions > Daily Threads post > Run workflow > `dry_run` (글과 사진만 만들고 게시 안 함, 결과는 Artifacts)
- **지금 바로 게시:** Run workflow > `force` (그래도 하루 1개 제한은 지킴)
- **잠시 멈추기:** Actions > Daily Threads post > `...` > Disable workflow
- 게시 기록과 사진은 `posts/` 폴더에 날짜별로 저장됨
