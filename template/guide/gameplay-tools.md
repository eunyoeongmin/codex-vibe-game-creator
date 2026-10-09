이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

# 플레이와 게임 설계 도구

현재 맡은 기능의 절만 읽는다. 명령의 Python과 decisions.py는 AGENTS.md에 적힌 프로젝트 경로를 사용한다. 아래 JSON 입력 파일도 프로젝트 안에 둔다. DB는 data/creator.sqlite이며 결정 기록과 연결되지만 별도의 제작 자료다.

## 플레이 저장과 실행 지점

플레이 슬롯은 게임 상태를 저장하고, 플레이 지점은 사용자가 다시 실행할 장면의 상태를 저장한다. 코드 파일 체크포인트와 다르다. 기존 상태 소유자·화면 진입·입력·시간·오디오 수명 처리를 확인하고 저장 가능한 JSON 상태만 추출한다. 게임 객체·함수·DOM을 직렬화하거나 eval로 복원하지 않는다.

`gameplay runtime`으로 game-tools/gameplay-runtime.js를 배치하고 게임 HTML에 연결한다. 이 명령만으로 게임에 연결됐다고 보고하지 않는다. 게임 초기화 뒤 `GameCreatorPlay.register({id,version,capture,restore,validate,migrations})`를 실제 게임 함수와 연결한다. id는 프로젝트 게임 고유의 안정된 문자열, version은 1부터 시작하는 저장 형식 버전이다. capture는 JSON 객체나 배열을 반환한다. restore(state)는 기존 루프를 중복 생성하지 않고 상태·화면·입력 가능 상태를 함께 복원한다. validate(state)는 허용 상태면 true를 반환한다. 비동기 함수도 가능하며 완료 후 resolve한다.

migrations는 이전 버전을 키로 다음 한 버전으로 옮기는 순수 함수다. 예: migrations[1]은 v1 상태를 받아 v2 상태를 반환한다. 원본과 실행 중 상태를 바꾸지 않는다. 건너뛴 버전의 변환이 없거나 미래 버전이면 거부한다. 변환과 복원은 따로 호출된다. 대시보드는 복원 전 현재 상태를 별도 backup으로 보관하고, 변환본을 migration으로 저장한 뒤 적용한다. 원본은 남긴다. 실패 시 런타임이 이전 상태로 복원을 시도하며 실패 사실을 숨기지 않는다.

사용자는 미리보기에서 게임을 열고 제작 도구의 플레이 저장에서 슬롯 또는 지점을 저장·불러온다. 어댑터가 없으면 연결 요청으로 안내한다. 등록만 해두고 날짜·장비·퀘스트 등이 실제로 복원된다고 추정하지 않는다. 현재 게임의 승인된 저장 범위에 해당하는 상태를 연결한다.

CLI: `gameplay save play_save --input file.json`, `gameplay list play_save`, `gameplay show play_save ID`. 저장 입력: name, kind(slot/point/backup/migration), entry(HTML 상대 경로), snapshot({adapter,version,state}), 선택 parent_id. 실제 캡처한 상태를 저장하며 가상의 플레이 이력을 만들지 않는다. 저장은 새 기록을 만들므로 이전 슬롯을 덮어쓰지 않는다.

## 게임 문구 다국어

대시보드 언어와 게임 언어는 독립적이다. 현재 게임의 문구 원본과 호출부를 찾아 JSON `{ "ko": {"item.count":"수량 {count}"}, "en": {"item.count":"Count {count}"} }` 형태의 실제 사용 파일을 연결한다. 예시는 형식 설명이며 게임에 샘플 문구를 추가하라는 뜻이 아니다. 기존 안정된 번역 체계가 있으면 연결 방식을 유지하고 이 편집기 형식으로 무단 교체하지 않는다. 지원 언어는 사용자 결정 범위를 따른다.

`gameplay save localization --input file.json`: name, path(기존 게임 JSON 상대 경로), base_locale. 변경 시 id와 --revision을 전달한다. 편집기는 언어별 문자열 값과 언어 추가를 지원하고 키 이름은 보존한다. `{name}` 변수의 집합이 원문과 다르면 저장을 거부하고, 빈 번역은 누락으로 표시한다. 변경 전 파일은 data/localization-history/에 보관한다.

기본 런타임 연결은 `gameplay runtime` 이후 GameCreatorStrings.load(url,{base,locale}), text(key,values), setLanguage(locale)이다. game-language-change 이벤트에서 현재 화면을 다시 그리도록 게임 코드에 연결한다. 빈 번역은 기준 언어로 대체한다. 문구를 innerHTML에 넣지 않는다. 기존 다국어 구현을 유지하면 해당 API에 어댑터를 연결한다.

표시 DOM에 data-game-string="키"를 붙이면 대시보드가 현재 화면의 넘침을 키와 언어에 연결한다. 숨겨진 화면·Canvas 문구까지 검사한 것으로 말하지 않는다. Canvas는 해당 엔진의 레이아웃 근거를 별도로 확인한다. 편집 내용을 화면에서 보려면 카탈로그를 다시 불러오거나 미리보기를 새로 연다.

## 플레이 비교

설계 담당은 사용자 원문과 판단할 차이를 바탕으로 2~4개 후보를 만든다. 비교할 요소, 유지할 조건, 같은 플레이 구간과 관찰 기준을 명시한다. 후보 간 배경·보상·적 구성 등 관련 없는 차이를 넣지 않는다. 랜덤 결과가 비교를 흐리면 동일한 시드·시작 상태를 사용한다. 이는 가설 비교이며 재미 점수나 자동 우승안을 만들지 않는다.

`gameplay save experiment --input file.json`: name, user_quote, hypothesis, entry, variable, invariants, observation, candidates:[{name,change}]. list/show도 가능하다. 수정은 id와 --revision을 함께 전달한다.

대시보드가 같은 원본에서 후보 폴더를 만들면 사용자가 각 후보 제작 요청을 보낸다. 구현 담당은 기존 variant 작업 경계 안에서 해당 가설만 구현한다. 원본을 바꾸지 않는다. 사용자가 실제 플레이 후 후보와 선택 이유를 고르면 기존 비교안 채택 절차로 파일을 반영하고 선택 내용·원문·설계 가설을 user_decisions에 남긴다. 후보가 생성됐다는 사실만으로 구현됐거나 플레이가 확인됐다고 보고하지 않는다. 탈락 후보는 자동 삭제하지 않는다.

## 기존 시스템 연결 설계

상태 변경 요청은 관련 기존 동작의 진입점·공통 처리·종료 후 화면까지 연결해서 다룬다. 예를 들어 날짜 변경은 실제로 있는 하루 종료 처리와 관계를 조사하되, 수면 연출·자원 소모 등 미승인 규칙을 자동 추가하지 않는다. 관련 없는 전체 시스템 조사로 확대하지 않는다. 기존 근거가 없는 연결과 사용자 선택이 필요한 부분을 구별한다. 이미 승인된 방향 안의 제작 선택은 작업 결정에 남긴다.

`relation list/show`와 `context search`로 관련 근거를 좁힌다. 등록되지 않은 코드 관계는 파일 근거를 확인하고 relation add로 연결한다. 키워드가 나온다는 사실은 기능적 연결의 증거가 아니다.

`gameplay save integration --input file.json`: name, user_quote, hypothesis, fingerprint(relation list의 현재 값), node_ids(관련 그래프 노드 ID 목록), flow:[{action,state_change,existing_connection,unresolved}]. 해당 없음은 그 이유를 적는다. 실제 신규 시스템이라 근거가 없으면 node_ids를 비워 두고 existing_connection에 조사 결과를 적는다.

사용자는 표에서 흐름을 검토·수정·승인할 수 있다. 구현 요청을 받으면 기존 상태 소유자와 공통 처리를 사용해 연결한다. 근거가 바뀌면 해당 부분만 다시 확인한다. 승인 범위를 바꾸는 새 선택만 사용자에게 묻고 일반 구현 순서마다 승인을 요구하지 않는다.

## 콘텐츠별 플레이 차이

`gameplay save content_plan --input file.json`: name, user_quote, hypothesis, target_count(명시적인 목표 수), units:[{name,situation,player_action,reuse,outcome}]. 목표 수는 사용자 결정에 맞추며 도구 한도(200) 때문에 사용자의 전체 목표를 축소하지 않는다. 그 이상이면 범위가 명시된 묶음으로 나눈다.

각 단위는 새 상황, 달라지는 플레이어 행동·선택, 앞서 배운 것 활용, 완료 후 변화를 가진다. 장르에 맞는 값으로 채우며 전투·보상을 공통 필수로 만들지 않는다. 스토리 원문 작성은 독립 스토리 담당으로 전달한다. 목표 수와 구성 수 차이, 완전히 같은 구성 행을 표시한다. 문장이 다르다는 사실로 플레이 차이나 재미가 검증됐다고 판단하지 않는다.

사용자 승인 후 구현 요청에서 선택된 구성을 코드·데이터에 연결한다. 이미 승인된 개수만으로 AI가 만든 세부 콘텐츠가 사용자 확정이라고 판단하지 않는다.

## 구현 연결 기록

세 설계 도구는 제안, 사용자 선택, 실제 구현 근거를 구분한다. UI에서 선택한 원문은 user_decisions에 저장된다. AI의 기술·제작 선택은 기존 work 규칙에 따라 저장한다. 관련 기록 원문과 선택 이유는 설계 이력에도 남는다.

승인된 설계를 구현했다면 `gameplay applied experiment|integration|content_plan --input file.json --revision 현재값`을 사용한다. 입력은 id, work_ids(현재 프로젝트의 active 작업 결정), note, evidence:[{path,quote}]다. 현재 게임 파일의 정확한 인용과 해시를 보관한다. 구현 기록은 사용자 만족·재미 판정이 아니다. CLI는 사용자 승인을 생성하지 않는다.
