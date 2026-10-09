# threads-daily-post

Threads **@jinggle_m** 게시 도구. 자동 게시하지 않고, 사용자 승인을 받은 뒤에만 수동으로 실행해요.

## 하는 일

- 게시 일정 자동 실행 없음. 초안을 확인하고 승인한 뒤에만 **하루 최대 1개** 게시
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

- **초안 생성:** Actions > Daily Threads post > Run workflow > `dry_run` (글과 사진만 만들고 게시 안 함, 결과는 Artifacts)
- **승인 후 게시:** 사용자가 해당 초안을 명확히 승인한 뒤에만 Run workflow > `force` (하루 1개 제한 유지)
- **잠시 멈추기:** Actions > Daily Threads post > `...` > Disable workflow
- 게시 기록과 사진은 `posts/` 폴더에 날짜별로 저장됨
