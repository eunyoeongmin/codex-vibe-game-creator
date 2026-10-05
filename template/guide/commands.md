이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

## 저장·조회 명령

아래의 ID와 내용은 형식 예시다. 실제 프로젝트와 사용자 발언으로 바꿔 사용한다.

```powershell
# 현재 프로젝트의 결정: 기본 최근 10건. 더 필요하면 --offset 10 등으로 조회한다.
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" user list

# 장르 중 확정된 항목 조회
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" user list --category genre --status confirmed

# 키워드 검색 / Semantica 의미 검색
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" user search '검색어'
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" user search '검색어' --semantic

# 특정 기록의 원문과 상태 조회
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" user show 'U-001'

$decisionInput = @{
    category = 'genre'
    topic = '장르'
    decision = '사용자가 선택한 장르'
    status = 'confirmed'
    user_quote = '사용자 발언 원문'
    assistant_reply = '관련 AI 답변 원문'
    ai_role = 'explanation'
} | ConvertTo-Json
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$decisionInput | & "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" user add
```

UTF-8 JSON 파일은 `user add --input 파일경로`로 입력한다. AI가 `status`를 정할 때 위 규칙에 따라 입력하고, 이후에는 저장된 값을 따른다. 검색 순위는 확정 여부를 바꾸지 않는다. 오류가 나면 저장 완료로 보고하지 않는다.

저장과 의미 검색은 기존 다국어 모델 캐시를 로컬에서 사용한다. 원문은 자르지 않고 보존한다. 전체 원문·메타데이터 조회와 키워드 검색은 임베딩 모델을 로드하지 않는다. 자동 다운로드나 외부 모델 API 호출을 하지 않는다.
