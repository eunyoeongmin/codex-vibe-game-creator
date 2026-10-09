이 문서는 AGENTS.md의 일부이며, 규칙이 충돌하면 AGENTS.md를 따른다

# 사운드 연출과 게임 밸런스

두 절은 독립적이다. 현재 배정받은 절만 읽는다. 명령 실행 파일은 AGENTS.md의 Python·decisions.py 경로를 사용한다. 설정과 비교 기록은 프로젝트 data/creator.sqlite에 저장하며 기록만으로 사용자의 게임 방향을 확정하지 않는다. 기존 사용자 결정·작업 결정의 경계를 따른다.

## 사운드 연출

등록된 sound 에셋으로 게임 상황별 재생 규칙을 구성한다. 음원 생성 기능이 아니다. 기존 사운드 호출·장면 전환·중지 경로를 찾아 승인된 이벤트에만 연결한다. 게임에 없는 연출이나 음성을 임의로 추가하지 않는다. 스토리 대사 작성은 독립 스토리 담당의 범위다.

`soundscape save --input file.json [--revision 현재값]`, `soundscape list`, `soundscape show ID`, `soundscape publish ID --revision 현재값`을 사용한다. 수정 입력에는 id가 필요하다.

입력 형식:
- name: 구성 이름
- buses: music/effect/ambient/voice별 0~1 음량
- duck_music: 음성 재생 중 배경음 비율(0~1)
- cues: 아래 항목의 배열(1~100)
  - key: 게임에서 호출할 고정 키. 영문자로 시작하며 영문·숫자·밑줄·점·하이픈 사용
  - name: 표시 이름, event: 사용 상황과 발생 조건
  - role: music / effect / ambient / voice
  - asset_id, path: 등록된 사운드 에셋 ID와 해당 파일의 프로젝트 상대 경로
  - gain: 0~1 음량, loop: 반복 여부
  - loop_start, loop_end: 반복 구간의 초 단위 위치. end=0은 파일 끝. 실제 음원 길이는 재생 시 확인한다.
  - fade_in, fade_out: 0~30초
  - priority: 0~100 정수, max_voices: 같은 호출 키의 최대 동시 재생 수 1~16

저장 시 에셋 버전과 파일 해시를 기록한다. 에셋 또는 파일이 바뀌면 재검토·저장해야 미리듣기·배포할 수 있다. 대시보드의 ‘믹싱 들어보기’에서는 역할별 음량, 동시 재생, 역할별 정지를 직접 조절한다. 이 화면의 슬라이더는 미리듣기 전용이며 파일에 적용하려면 편집 화면에서 저장한다. 사운드 파일 미리듣기는 기존 에셋 미리보기의 16MB 제한을 따른다. 브라우저 코덱 미지원·재생 차단은 오류로 보고하며 성공했다고 말하지 않는다.

publish는 content/soundscapes/ID.json과 game-tools/sound-runtime.js, balance-runtime.js를 생성하고 이전 파일을 보관한다. 생성만으로 게임 연결이 끝난 것이 아니다. HTML에 sound-runtime.js를 연결하고 `const audio = GameCreatorAudio.create()`로 게임 오디오 소유자를 하나 둔다. `await audio.load(configURL,{baseURL:게임루트URL})` 다음, 사용자의 시작·재생 입력에서 `await audio.unlock()`을 호출한다. 이후 실제 게임 이벤트에서 `audio.play(key)`를 호출하고 화면 이탈·게임 종료에서 `audio.stop(role)` 또는 `audio.stopAll()`을 연결한다. 중복 오디오 시스템을 새로 만들어 기존 소리와 겹치지 않는다.

music 재생은 기존 music을 각 항목의 fade_out으로 종료하며 새 음악은 fade_in으로 시작한다. effect/ambient/voice는 별도로 유지된다. 반복 구간 이전 부분은 처음 한 번 재생한다. 같은 소리가 max_voices에 도달하면 가장 오래된 같은 키의 소리를 즉시 교체한다. 전체 64개에 도달하면 낮은 우선순위를 교체하고, 새 소리의 우선순위가 모두보다 낮으면 생략한다. voice가 남아 있는 동안 music에 duck_music을 적용하고 마지막 voice가 끝나면 복원한다. 음량 0과 역할 정지는 다르다. 일시정지·장면 전환에 필요한 정지 범위는 해당 게임의 승인된 규칙에 맞춘다.

`audio.setVolume(role,0~1)`, `audio.status()`, `audio.dispose()`를 사용할 수 있다. 페이지를 벗어나거나 오디오 소유자를 교체할 때 dispose로 소스와 AudioContext를 정리한다. 설정의 event 설명만으로 게임 이벤트가 자동 연결되지는 않는다. 구현 담당이 실제 발생·중지 지점과 작업 결정 근거를 남긴다. 게시한 구성의 음원은 사용 중 에셋 표시와 별도로 게임 내보내기에 포함된다.

## 게임 밸런스 비교

게임이 실제 사용하는 계산 함수를 연결한다. 비교용으로 비슷한 공식을 새로 써서 게임의 계산이라고 보고하지 않는다. 기존 코드에 계산과 부작용이 섞여 있으면 승인 범위 안에서 순수 계산을 분리하고 게임과 비교 어댑터가 같은 함수를 호출하게 한다. 가상의 게임 수식이나 장르 기본값을 임의로 등록하지 않는다.

`balance runtime`은 게임용 런타임을 배치한다. 게임 HTML에 balance-runtime.js를 연결하고 초기화 시 `GameCreatorBalance.register({id,version,calculate})`를 호출한다. calculate(inputs)는 실제 게임 함수를 호출해 `{출력키:유한한 숫자}`를 반환한다. Promise도 가능하다. 입력 객체를 수정하거나 실행 중 게임·저장 상태를 변경하지 않는다. 한 조건의 계산은 유한하고 짧게 끝내며 무제한 시뮬레이션을 넣지 않는다. 의도된 랜덤 계산이라면 시드를 입력에 포함해 동일 조건을 재현하고 무작위 결과를 확정 수치로 표현하지 않는다.

`balance save --input file.json [--revision 현재값]`, `balance list`, `balance show ID`로 등록한다. 입력:
- name, entry(기존 HTML 상대 경로), adapter(등록한 id), adapter_version(등록한 version)
- parameters: key, label, min, max, default, step을 가진 숫자 입력 배열(1~20). 기본값은 현재 게임 값이다.
- 선택 parameters[].binding: {dataset,row_id,field}. 기존 content register로 등록된 실제 숫자 필드에 연결하며 default는 현재 값과 일치해야 한다.
- outputs: key, label, unit을 가진 숫자 출력 배열(1~20)
- evidence: {path,quote} 배열. 실제 게임 계산 코드의 파일과 정확한 원문 인용이다. 코드를 수정하면 어댑터 버전과 등록 근거도 함께 갱신한다.

대시보드의 수치 비교는 별도 미리보기 프레임에서 실제 게임을 열어 어댑터를 호출한다. 현재 플레이 프레임을 건드리지 않는다. 사용자는 최대 20개 입력 조건과 출력별 목표 최솟값·최댓값을 지정한다. 목표를 비워 두면 결과 수치만 보여준다. 목표 안/낮음/높음은 지정한 숫자 범위와 비교한 결과이며 재미나 적정 난도의 판정이 아니다.

계산 코드·연결 데이터의 근거와 실행 전후 게임 파일 해시를 확인하고, 변동이 생기면 다시 연결하거나 계산하도록 안내한다. 결과는 balance_run에 입력·출력·목표·근거와 함께 저장한다. 계산 중 오류, 무한값, 누락 출력은 실패로 보여주며 다른 공식이나 목표로 바꿔 통과시키지 않는다. 15초 동안 응답이 없으면 해당 프레임을 종료한다. 어댑터가 실제 함수를 호출하는지는 연결 작업에서 확인하며 런타임이 함수 의미를 자동 증명한다고 보고하지 않는다.

비교 결과만으로 게임 수치를 수정하지 않는다. 사용자가 ‘이 결과로 조정 요청’에서 적용할 조건·변경을 지정하면 해당 등록 콘텐츠 행 또는 실제 게임 데이터만 바꾸고 작업 결정에 이유·결과 기록 ID를 남긴다. 새 게임 방향이나 기존 확정 결정 번복이 필요한 경우에는 기존 결정 절차를 따른다. 시뮬레이션 결과로 사용자의 취향이나 재미를 확정하지 않는다.
