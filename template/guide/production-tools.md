이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다.

# 화면·관계·연출 도구

직접 수행하는 작업에 해당하는 절만 읽는다. 아래 decisions.py 명령의 실행 경로는 AGENTS.md의 실행 환경을 사용한다.

## 화면 지정 요청

- 사용자가 캡처하거나 첨부한 정지 이미지에 영역을 표시한다. 원본 이미지, 크기, 0~1 비율의 사각형 좌표와 영역별 설명을 feedback 기록에 보존한다. 좌표 기준은 게임 캔버스가 아니라 캡처 이미지 전체다.
- 캡처 이미지는 정지해 있지만 게임 자체의 시간·네트워크·상태가 정지했다고 가정하지 않는다. 원문·영역·이미지를 함께 보고 실제 코드·에셋의 대상을 확인한 뒤 요청 범위를 수정한다.
- 영역이 캐릭터인지 버튼인지 자동으로 판별됐다고 주장하지 않는다. 대상이 구분되지 않으면 필요한 부분만 확인한다.
- comparison_to는 사용자가 추가한 수정 전후 이미지의 연결이다. 비교 이미지 등록을 결과 승인으로 취급하지 않는다.

## 데이터 관계

- `decisions.py relation list`는 등록된 콘텐츠 참조 필드, 스토리 링크, 결정·레퍼런스 연결, 에셋 파일과 기록 연결, 타임라인에서 사용하는 스토리·에셋을 보여준다. 노드 ID는 결과의 id 문자열을 그대로 쓴다.
- `decisions.py relation show <노드 ID>`는 연결과 코드의 출현 위치를 구분하여 반환한다. 코드의 문자열 일치는 동작 연결의 증거가 아니다. 조회 한도에 도달했거나 데이터 파일을 읽지 못한 경우 관계가 없다고 결론 내리지 않는다.
- 코드에서 확인한 동작 연결은 `decisions.py relation add --input <JSON 경로>`로 기록한다. JSON은 source, target(노드 ID), relation(연결 의미), user_note(사용자 원문), interpretation(담당의 해석), evidence를 가진다. evidence는 path(프로젝트 상대 경로), line(1부터), quote(해당 줄부터의 정확한 원문)를 사용한다. 스크립트가 현재 파일과 원문을 대조하고 파일 해시를 보존한다.
- 파일이 바뀌면 stale, 대상이 사라지면 missing으로 표시한다. 이런 근거는 재확인 전까지 현재 동작의 근거로 사용하지 않는다. 사용자·AI가 작성한 연결 의미와 확인된 파일 인용을 구분한다.
- 관계 수정 요청은 선택 대상, 연결 근거, 사용자 원문을 관련 담당에게 전달한다. 하루 경과 같은 공통 상태 변경을 수정할 때는 연결된 기존 처리를 확인하며 새 게임 규칙을 임의로 추가하지 않는다.

## 연출 타임라인

- 편집 가능한 동작은 dialogue, move, sound, image, transition, wait다. 순서, 앞 간격(delay 초), 길이(duration 초), 대상과 에셋을 저장한다. 단계 ID는 유지하고 순서만 변경한다.
- `decisions.py timeline list / show <id>`로 조회한다. `timeline save --input <JSON 경로>`는 name과 steps 배열을 받는다. 수정은 기존 id 및 `--revision`을 전달한다. 단계마다 id, kind, delay, duration을 기록한다. duration은 0.05초 이상이다.
- move는 target, x, y(현재 위치에서 이동할 px), sound/image는 asset_id와 asset_path, dialogue는 story_id와 선택적 excerpt(확정 스토리 원문의 정확한 일부), transition은 color(#RRGGBB)를 사용한다. 에셋·스토리의 버전을 보존하며 변경되면 검토 후 다시 저장한다.
- 대사는 스토리 작업실의 확정된 원문에서 선택한다. 미정인 대사나 새 사건을 타임라인 담당이 만들어 채우지 않는다. 이야기 작성은 독립 스토리 담당에게 전달한다.
- `timeline publish <id> --revision <revision>`은 content/timelines/<id>.json 및 game-tools/timeline-player.js를 생성한다. 이전 파일은 data/timeline-history/에 보관한다. 파일 생성과 게임 연결은 별개다.
- 실제 연결 담당은 HTML에서 재생 스크립트를 로드하고, 승인된 발생 조건에서 `await GameCreatorTimeline.load('content/timelines/<id>.json', {baseURL: new URL('./', location.href)})`를 호출한다. baseURL은 에셋 경로의 기준인 게임 루트를 정확히 지정한다. 중첩 HTML에서는 상대 경로를 그 위치에 맞춘다. 새 발생 조건을 임의로 정하지 않는다.
- DOM 이동 대상은 data-timeline-target="대상 ID", 선택적 data-timeline-label="표시 이름"을 붙인다. CSS 선택자도 사용할 수 있다. Canvas·게임 엔진은 `GameCreatorTimeline.registerTarget(id, label, async (step, context) => { ... })`로 기존 게임 객체에 연결한다. target 핸들러는 duration에 맞게 처리하고 context.signal 중단 시 멈춘다. context.preview면 원상 복구 함수를 반환한다. 게임 상태·충돌 좌표를 CSS만으로 바꾼 척하지 않는다.
- 반환된 Promise가 완료되면 기존 게임의 입력·상태를 복구한다. 필요한 입력 잠금·일시정지는 게임의 기존 처리로 연결하며 재생 코드가 모든 엔진을 자동 정지시킨다고 가정하지 않는다. `GameCreatorTimeline.stop()`은 재생 중단에 사용한다.
- 대시보드 재생은 별도 미리보기에서 수행하며 완료·중단 후 기본 DOM 이동을 되돌린다. 일반 게임 재생은 이동 결과를 유지한다. 소리 재생이 브라우저에 차단되면 오류를 그대로 전달한다.
- 게임 내보내기는 실제 발행된 타임라인이 사용하는 미디어도 포함한다. 편집만 하고 발행하지 않은 버전을 적용됐다고 보고하지 않는다.
