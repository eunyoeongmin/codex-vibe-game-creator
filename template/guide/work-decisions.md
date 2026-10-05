이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

## 작업 결정 기록

저장소: `data/decisions.sqlite`, 테이블: `work_decisions`.

작업 결정 기록은 게임 제작 AI가 구현 중 내린 기술·제작 선택과 근거를 담는다.
사용자 결정 기록의 category에 해당하는 사용자 결정은 그쪽에만 저장하고 작업 결정에는 저장하지 않는다.

### 목적
게임 제작 중 내린 결정을 잊거나 서로 충돌하는 것을 막고, 나중에 "왜 그랬는지"를 찾을 수 있게 한다. MD 메모를 매번 전부 읽는 방식은 쓰지 않는다. 필요한 것만 조회한다.

### 저장 조건 (하나라도 해당하면 저장)
- 여러 선택지 중 하나를 골랐고, 되돌리는 데 비용이 든다
- 사용자가 구현 방식을 직접 지시했다
- 이전 결정을 번복하거나 수정한다
- 같은 문제로 두 번 이상 막혔다가 방법을 정했다

저장하지 않는 것: 변수명, 포맷팅, 단순 버그 수정, 사소한 구현 선택

### 테이블 구조
```sql
CREATE TABLE work_decisions (
  id            TEXT PRIMARY KEY,      -- 자동: W-001, W-002 ...
  created_at    TEXT NOT NULL,         -- 자동
  project_id    TEXT NOT NULL,         -- 필수. 없으면 저장 거부
  area          TEXT NOT NULL,         -- 허용 목록: gameplay, art, ui, code_structure, content, other
  decision      TEXT NOT NULL,         -- 무엇을 정했나 (1문장, 이유는 섞지 않음)
  reason        TEXT NOT NULL,         -- 왜 (1~3문장, 300자 이내)
  alternatives  TEXT NOT NULL,         -- 버린 선택지와 이유, 없으면 "없음"
  evidence_type TEXT NOT NULL,         -- user / file / commit / test / none
  evidence_ref  TEXT,                  -- none이 아니면 필수 (발언 원문 일부, 경로, 해시 등)
  source        TEXT NOT NULL,         -- user_instruction(사용자 지시) / ai_judgment(네 판단)
  status        TEXT NOT NULL DEFAULT 'active',  -- 자동: active / superseded
  supersedes    TEXT,                  -- 번복한 이전 결정 id
  superseded_by TEXT                   -- 자동
);
```
- 네가 입력하는 것: area, decision, reason, alternatives, evidence_type, evidence_ref, source, supersedes
- 스크립트가 채우는 것: project_id(.project 마커), id, created_at, status, superseded_by

### 저장 명령
```
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" work add --area <영역> --decision "..." --reason "..." --alternatives "..." \
  --evidence-type <유형> --evidence-ref "..." --source <출처> [--supersedes <id>]
```

- 저장 후 결정 id를 코드 주석이나 커밋 메시지에 남긴다 (예: `# W-023`, `refs W-023`)

### 스크립트가 구현해야 할 검증 (지시문에 맡기지 말고 코드로 강제)
- project_id가 없거나 비어 있으면 저장 거부
- area가 허용 목록 밖이면 거부
- reason이 비어 있거나 300자를 넘으면 거부
- evidence_type이 none이 아닌데 evidence_ref가 비어 있으면 거부
- evidence_type이 none이면 source는 ai_judgment만 허용 (근거 없는 결정이 사용자 지시로 위장되는 것 방지)
- 저장 직전에 같은 project_id·area의 active 결정을 출력하고, 겹치는 항목이 있는데 `--supersedes` 또는 `--independent` 중 하나가 없으면 거부
- `--supersedes`가 지정되면 이전 결정의 status를 superseded로, superseded_by를 새 id로 자동 갱신
- 전체 조회(`list --all`)는 만들지 않는다. 기본 출력은 최근 10건으로 제한한다

### 조회 조건 (아래 시점에는 반드시 조회)
1. 세션 시작 시: `& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" work recent --limit 10` 실행
2. 파일이나 모듈을 수정하기 전: `& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" work list --area <영역> --status active`
3. 새 결정을 저장하기 직전: 위 충돌 검사 출력을 확인
4. 코드나 설계에서 이유를 모르는 부분을 만났을 때: 추측하지 말고 `& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" work why <id>` 또는 `& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" work search "<키워드>"`를 먼저 실행
5. 사용자가 "왜 그렇게 했어?"라고 물을 때: 기록을 조회해서 답한다. 기록이 없으면 "기록 없음, 추정은 이렇다"라고 구분해서 말한다

### 번복 규칙
- source가 ai_judgment인 결정은 근거를 대고 번복할 수 있다.
- source가 user_instruction인 결정은 사용자 확인을 받은 뒤에만 번복한다.



