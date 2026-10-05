이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

## topic 추가 기록

최종 사용자의 게임 제작 중 [제품 설계 category·topic 표](../catalogs/product-design-topics.md)에 새 항목이 필요해지면 표 추가와 근거 보존을 함께 수행한다. 표를 직접 수정한 뒤 기록을 생략하지 않는다. 기본으로 제공된 항목이나 하네스 개발 대화를 게임 프로젝트의 추가 이력으로 저장하지 않는다.

저장소는 `data/decisions.sqlite`의 별도 테이블 `topic_additions`다. 원문과 추가 내용은 SQLite에 보존하고, 검색 벡터를 함께 저장하여 Semantica 의미 검색에 사용한다. 이 기록은 표에 항목을 추가한 경위이며 사용자 게임 방향의 확정 기록을 대신하지 않는다.

| 항목 | 저장 내용 |
| --- | --- |
| id, created_at | 자동 ID `T-001`과 저장 시각 |
| project_id | 필수. 항목 추가가 필요해진 게임 프로젝트 |
| category, topic, description | 추가할 분류, 항목 이름, 표의 '정할 내용' 설명 |
| user_quote | 추가의 계기가 된 사용자 발언 원문. 요약하지 않음 |
| ai_interpretation | 사용자 발언을 AI가 어떻게 해석했는지 |
| assistant_reply | 사용자에게 제시한 AI 답변 원문. 요약하거나 생략하지 않음 |
| reason | 기존 항목으로 처리하지 않고 새 항목을 추가하는 이유. 1~3문장, 300자 이내 |
| source | 사용자의 직접 지시이면 `user_instruction`, AI의 판단이면 `ai_judgment` |
| evidence_type, evidence_ref | `user`, `file`, `commit`, `test`, `none`과 구체적인 출처·근거. `none`이 아니면 근거 필수이며 `none`은 `ai_judgment`만 허용 |
| catalog_path, added_content | 스크립트가 기록하는 표 파일 경로와 실제로 추가한 행 |

- 먼저 표와 기존 기록을 조회하여 같은 의미의 항목이 있는지 확인한다. `topic search --semantic`으로 추가 이력의 관련 맥락도 찾을 수 있다.
- 새 항목이 필요하면 사용자 원문, AI 해석, AI 답변을 구분해서 입력한다. 해석을 사용자 원문으로 바꾸어 기록하지 않는다.
- `topic add`는 표에 행을 추가하면서 위 기록과 검색 벡터를 함께 저장한다.
- 추가한 topic에서 게임 방향을 제안하거나 확정할 때는 별도로 기존 사용자 결정 기록 규칙을 따른다. 표 추가 자체를 `confirmed`로 간주하지 않는다.

```powershell
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" topic add --input 'topic-추가.json'
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" topic list
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" topic show T-001
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" topic search '추가 이유'
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" topic search '추가 이유' --semantic
```

`topic add`는 UTF-8 JSON 파일 또는 stdin을 받는다. 입력에는 `category`, `topic`, `description`, `user_quote`, `ai_interpretation`, `assistant_reply`, `reason`, `source`, `evidence_type`, 필요한 `evidence_ref`를 넣는다. 표의 두 셀인 `topic`과 `description`은 줄바꿈과 `|` 없이 입력하며 사용자 원문·AI 답변의 줄바꿈은 그대로 보존한다.

