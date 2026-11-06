# InsightBay 공고 알림

[인사이트베이 하이포지션](https://www.insightbay.co.kr/v2/positions)에 원하는 키워드(예: BCG, Bain)가 제목에 들어간 공고가 올라오면 Slack/Discord로 알림을 보냅니다.

- GitHub Actions에서 10분마다 자동 실행 (내 컴퓨터가 꺼져 있어도 동작)
- 공개 저장소로 쓰면 비용 0원

알림 예시:

```
🔔 새 공고: [인턴/RA][BCG] SR 채용 공고 (AX, Data)
마감일: 2026-11-13
https://www.insightbay.co.kr/v2/positions/view/366/1
```

## 설정 방법 (10분)

### 1. 내 저장소 만들기

이 페이지 오른쪽 위 **Use this template → Create a new repository** 를 누릅니다.

- Repository name: 아무거나 (예: `insightbay-watcher`)
- **Public** 으로 선택 (Private이면 GitHub Actions 무료 한도를 넘습니다)

### 2. 알림 받을 웹훅 주소 만들기

**Slack**

1. https://api.slack.com/apps → **Create New App** → **From scratch** → **Pick features**
2. 앱 이름 입력, 알림 받을 워크스페이스 선택, **Incoming Webhooks** 선택 후 생성
3. 왼쪽 메뉴 **Incoming Webhooks** → 켜기 → **Add New Webhook** → 채널 선택
4. `https://hooks.slack.com/services/...` 주소 복사

**Discord**

알림 받을 채널 ⚙️ → **연동** → **웹후크** → **새 웹후크** → **웹후크 URL 복사**

> 웹훅 주소는 비밀번호처럼 다루세요. 아는 사람은 누구나 그 채널에 메시지를 보낼 수 있습니다.

### 3. 웹훅 주소와 키워드 등록

내 저장소의 **Settings → Secrets and variables → Actions** 에서:

| 탭 | 이름 | 값 |
|---|---|---|
| Secrets → New repository secret | `WEBHOOK_URL` | 2번에서 복사한 주소 |
| Variables → New repository variable | `KEYWORDS` | 쉼표로 구분한 키워드, 예: `BCG,Bain,Kearney` |

키워드는 대소문자를 구분하지 않으며, 나중에 여기서 바꾸면 다음 실행부터 적용됩니다.

### 4. 첫 실행

**Actions** 탭 → (안내가 나오면 **I understand my workflows, go ahead and enable them**) → 왼쪽 **InsightBay watcher** → **Run workflow**

초록색 ✅ 이 뜨면 완료입니다. 이후 10분마다 자동으로 확인합니다.

## 자주 묻는 것

**알림이 언제 오나요?**
키워드에 맞는 *새* 공고가 올라온 뒤 다음 실행 때 옵니다. GitHub 사정에 따라 몇 분~십수 분 늦을 수 있습니다. 이미 올라와 있던 공고는 알리지 않습니다.

**실행 기록은 어디서 보나요?**
**Actions** 탭. 실행을 눌러 `watch` → `Check for new positions` 로그에서 `Checked N positions, sent M notifications` 를 확인할 수 있습니다.

**❌ 실패 메일이 왔어요.**
- `KEYWORDS and WEBHOOK_URL environment variables are required` → 3번 설정을 확인하세요.
- `No positions parsed` → 인사이트베이 페이지 구조가 바뀐 것입니다. 원본 저장소 관리자에게 알려주세요.
- 웹훅 관련 오류 → 웹훅 주소가 삭제됐거나 바뀐 것입니다. 새로 만들어 `WEBHOOK_URL` 을 바꿔주세요. 못 보낸 알림은 다음 실행 때 다시 보냅니다.

**알림이 갑자기 안 와요.**
GitHub은 60일간 저장소 활동이 없으면 예약 실행을 끕니다. **Actions** 탭에서 다시 켜주세요.

**같은 공고 알림을 다시 받고 싶어요.**
`seen.json` 에서 그 공고 번호(링크의 `/view/숫자/`)를 지우면 다음 실행 때 다시 알립니다.
