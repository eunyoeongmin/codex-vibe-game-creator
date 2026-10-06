이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

## 레퍼런스 기록

레퍼런스는 결정 자체가 아니라 결정의 재료다. `data/decisions.sqlite` 안의 별도 테이블 `user_references`에 보존한다.

조사·해석·적용의 근거와 변경 이력은 [레퍼런스 추적 기록](reference-tracing.md)을 따른다. 제목·참고 요소만 저장한 것으로 조사를 완료 처리하지 않는다.

| 항목 | 값 |
| --- | --- |
| id | 자동: `R-001`, `R-002`, … |
| project_id | 필수. 없거나 비어 있으면 저장 거부 |
| kind | `game`, `image`, `link`, `video`, `other` |
| title_or_url | 게임 이름이나 링크, 이미지의 제목 |
| file_path | 이미지 파일을 보관한 프로젝트 폴더 안의 상대 경로. 없으면 비움 |
| user_note | 사용자가 한 말 원문. 요약하지 않음 |
| aspects | `art_style`, `camera`, `ui`, `color`, `combat`, `mood`, `other` 중 복수 선택한 값의 배열. 아직 고르지 않았다면 `[]` |

이미지 바이트는 DB에 넣지 않는다. `reference add`에 프로젝트 폴더 안의 이미지 원본 경로를 주면 `references/<project_id>/R-번호.확장자`로 복사하고 그 상대 경로를 저장한다. 원본 파일은 유지한다.

### 레퍼런스 규칙

- 사용자가 레퍼런스를 주면 `user_references`에 사용자 발언을 원문 그대로 저장한다.
- “이 게임처럼”, “이 게임 느낌으로”라는 말만으로 화풍·시점·UI 등을 추측해서 확정하지 않는다.
- 어떤 점을 참고하려는지 한 번 묻고 후보를 제시한다. 예: 화풍 / 카메라 / UI / 색감 / 전투 느낌. 사용자가 이미 참고할 요소를 말했다면 다시 묻지 않는다.
- 사용자가 고른 요소를 `aspects`에 반영하고, 그 요소에 관한 안만 해당 category의 `proposed`로 저장한다. 사용자가 승인하면 원문과 AI 답변을 함께 새 `confirmed` 기록으로 저장하고 `supersedes`로 연결한다.
- “화풍을 참고하자”는 참고 요소의 선택이다. “그럼 화풍은 픽셀로 하자”처럼 구체적인 게임 방향을 명시적으로 정했다면 기존 확정 판단 규칙에 따라 `confirmed`로 저장하며 해당 레퍼런스를 근거로 연결한다.
- 화풍은 `art_style`, 카메라는 `viewpoint`, UI는 `ui_style`, 색감은 `color_palette`, 분위기는 `mood`에 기록한다. 전투 느낌은 `other`의 해당 topic에 기록하고, 반복 행동 사이클을 정한 경우에는 `core_loop`에 기록한다.
- 사용자 결정의 `reference_ids`에 그 결정의 근거가 된 레퍼런스 ID를 남긴다. 레퍼런스 자체나 선택하지 않은 요소를 결정으로 저장하지 않는다.
- 사용자가 파일을 제공한 것이 아니라 웹 조사를 지시한 경우, 조사한 내용과 이미지를 보여주고 레퍼런스로 사용해도 괜찮은지 묻는다. 승인받은 자료를 저장한다. 자료를 레퍼런스로 채택하는 승인은 게임 방향의 확정과 구분한다.
- 레퍼런스의 에셋(이미지·음악·캐릭터)을 그대로 복제해 게임에 사용하지 않는다. 방향 참고용으로만 쓴다. 참고 이미지의 별도 보관과 게임 에셋으로의 사용을 구분한다.

### 레퍼런스 저장·조회 명령

```powershell
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" reference add --input '레퍼런스.json'
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" reference list
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" reference show R-001
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" reference search '검색어'
& "{{HARNESS_PYTHON}}" -B "{{HARNESS_DECISIONS}}" reference set-aspects R-001 --aspects art_style color
```

`reference add`는 UTF-8 JSON 파일 또는 stdin을 받는다. `kind`, `title_or_url`, `user_note`, `aspects`는 필수이며 `file_path`는 이미지 파일이 있을 때 입력한다. 아래는 형식 예시이며 원문과 파일 경로는 실제 자료로 바꾼다.

```json
{"kind":"image","title_or_url":"참고 이미지","file_path":"받은이미지.png","user_note":"이 이미지 느낌으로","aspects":[]}
```

`set-aspects`는 참고 요소만 바꾸며 최초 사용자 원문을 덮어쓰지 않는다. 요소를 고르거나 결정을 승인한 발언과 AI 답변은 해당 사용자 결정 기록에 보존한다. 결정의 `reference_ids`는 새 기록에서 생략하면 `[]`, `supersedes`로 이전 결정을 잇는 경우 생략하면 이전 연결을 유지한다. 연결을 바꾸려면 배열을 명시한다.


프로젝트 폴더 밖의 이미지 경로는 거부한다. 첨부 이미지는 먼저 현재 프로젝트 안에 보관한 뒤 그 경로를 입력한다.
