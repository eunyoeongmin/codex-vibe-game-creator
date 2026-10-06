이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

# 레퍼런스 조사·해석·적용 추적

기존 user_references의 원문·파일과 reference_ids 연결은 유지한다. 같은 프로젝트 DB의 reference_traces에 단계별 기록을 추가한다. RT-번호는 자동 생성되며 사용자 확정 여부를 뜻하지 않는다. 실제 조사·선택·적용 사실을 기록하고 빈 단계를 추측해서 채우지 않는다.

## 기록을 담당하는 주체

- 레퍼런스 담당: 실제 조사 근거(research), 사용자 선택에 대한 해석(interpretation)을 기록한다.
- 게임디자인·아트 담당: 해석을 적용하는 구체적인 설계와 원본과 달리할 점을 application의 planned로 기록한다. 기존 해석과 달라지면 먼저 interpretation을 변경 이유와 함께 갱신한다.
- 개발·아트 담당: 실제 적용 파일과 위치가 생기면 같은 application topic의 새 기록을 applied로 저장한다. 설계와 달라진 점과 이유를 남긴다. 채택하지 않은 안은 dropped로 기록한다.
- 오케스트레이터: 조사 결과·사용자가 고른 부분·AI 해석·적용 계획을 사용자에게 간결하게 보여준다. 검색 진행 표시나 기록 ID만으로 설명을 대신하지 않는다. 승인과 질문은 기존 사용자 결정·위임 범위 규칙을 따르고, 이 추적 기록을 이유로 세부사항마다 승인 절차를 추가하지 않는다.
- 담당은 반환할 때 레퍼런스 ID와 RT-번호를 함께 전달한다. 설계·결정·에셋의 원본은 복제하지 않고 ID와 적용 위치로 연결한다. 디자이너가 적용하려고 새로 정한 수치를 원본에서 확인한 수치로 쓰지 않는다.

## 명령과 공통 항목

AGENTS.md의 결정 명령 뒤에 아래 인자를 붙인다. 입력 JSON은 프로젝트 안의 UTF-8 파일 또는 stdin으로 전달한다.

```text
reference trace-add R-001 --input trace.json
reference show R-001
reference search "찾을 근거나 해석"
```

- 공통 필수 항목: stage, topic, user_quote, assistant_reply, reason. 사용자 원문과 해당 AI 답변은 요약으로 대체하지 않는다. reason은 최초 선택 또는 변경 이유다.
- 같은 레퍼런스의 같은 stage·topic에 기록이 있으면 supersedes에 현재 RT-번호를 지정해야 한다. 기록은 덮어쓰지 않으며 이전 내용·시각·변경 이유가 보존된다. 서로 다른 출처나 적용 대상은 구분되는 topic을 쓴다.
- show는 조사·해석·적용 이력과 연결된 사용자·작업 결정, 에셋을 함께 반환한다. search는 기존 제목·사용자 원문 외에 추적 기록의 내용도 키워드로 찾는다. 모델 없이 동작한다.
- 근거가 대체되면 이를 사용하던 해석·적용은 outdated_basis로 표시된다. 변경된 근거를 검토하고 새 기록으로 연결한다. 과거 기록은 보존하며, 대체된 근거를 새 해석·적용에 연결하는 것은 거부한다.

| stage | 추가 필수 항목 | 의미 |
|---|---|---|
| research | source, locator, observation, limitations | 실제 확인한 출처, 근거 위치, 관찰 내용, 확인하지 못한 부분 |
| interpretation | research_ids, meaning | 같은 레퍼런스의 research RT-번호 배열, 사용자 선택을 이해한 구체적인 의미 |
| application | interpretation_ids, plan, differences, state, decision_ids, asset_ids, files | 근거 해석 RT-번호 배열, 적용 설계, 원본·계획과 달라진 부분, 적용 상태, 결정·에셋 연결, 파일·위치 |

- source는 http(s) URL 또는 존재하는 프로젝트 내부 상대 파일 경로다. locator는 영상 시점·페이지·문단·이미지 영역 등이며 해당 없으면 빈 문자열로 둔다. limitations와 differences도 해당 없으면 빈 문자열로 둔다.
- research_ids와 interpretation_ids는 각각 하나 이상 필요하다. 같은 프로젝트·레퍼런스의 올바른 단계 기록만 연결한다.
- state는 planned / applied / dropped다. applied는 담당의 적용 기록이며 사용자 승인이나 검증 통과를 뜻하지 않는다.
- decision_ids는 같은 프로젝트의 U-번호·W-번호, asset_ids는 A-번호 배열이다. 연결할 기록이 없으면 빈 배열로 둔다.
- 연결한 에셋의 당시 revision은 asset_versions에 자동 보존된다. 이후 에셋이 바뀌어도 적용 기록 당시 버전을 구분할 수 있다. 과거 에셋 내용은 asset history로 조회한다.
- files는 `[{"path":"프로젝트 내부 상대 경로","location":"함수·선택자·구간 등 적용 위치"}]` 형식이다. planned나 dropped는 빈 배열을 사용할 수 있다. applied는 존재하는 파일과 구체적인 위치가 하나 이상 필요하다. 파일 존재 확인이 구현 의미까지 검증하지는 않는다.

다음은 입력 형식 예시다. 실제 자료를 확인하지 않고 예시 내용을 기록하지 않는다.

```json
{"stage":"research","topic":"영상의 공격 후 빈틈","user_quote":"전투 템포를 참고하자","assistant_reply":"확인한 장면과 확인하지 못한 부분을 정리했습니다.","reason":"선택한 전투 템포의 근거 조사","source":"https://example.com/video","locator":"00:12–00:18","observation":"공격 동작 종료 후 다음 행동까지 간격이 보인다.","limitations":"영상만으로 정확한 프레임 수는 확인하지 못했다."}
```

```json
{"stage":"interpretation","topic":"전투 템포","user_quote":"전투 템포를 참고하자","assistant_reply":"공격 후 빈틈을 읽고 반응하는 흐름을 참고하려는 것으로 이해했습니다.","reason":"선택한 참고 요소의 구체적인 해석","research_ids":["RT-001"],"meaning":"공격 후 빈틈이 다음 행동 선택에 영향을 주는 흐름. 정확한 수치 복제는 아님."}
```

```json
{"stage":"application","topic":"일반 공격 후 빈틈","user_quote":"그 부분을 참고해서 만들어줘","assistant_reply":"우리 게임의 공격 상태 전환에 빈틈을 적용하는 안입니다.","reason":"선택한 해석을 현재 전투 구조에 연결","interpretation_ids":["RT-002"],"plan":"공격 상태가 끝난 뒤 정해진 간격을 거쳐 다음 행동이 가능하게 한다.","differences":"간격의 초깃값은 우리 게임의 별도 설계값이며 원본 수치가 아니다.","state":"planned","decision_ids":[],"asset_ids":[],"files":[]}
```

적용 후에는 같은 topic으로 supersedes에 앞의 application ID를 넣고, state를 applied로 바꾸며 실제 files·관련 기록 ID·변경 이유를 포함한 전체 입력을 보낸다.
