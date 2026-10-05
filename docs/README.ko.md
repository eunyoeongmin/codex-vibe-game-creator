# Codex Vibe Game Creator

코딩 없이, 대화로 만드는 나만의 게임. 아이디어를 말하고 Codex와 기획을 구체화한 뒤, 로컬 웹 작업실에서 만들고 플레이합니다.

한국어 · [English](../README.md) · [日本語](README.ja.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md)

OpenAI의 공식 제품이 아닌 독립 커뮤니티 프로젝트입니다.

## 다운로드와 실행

**[최신 버전 다운로드](https://github.com/eunyoeongmin/codex-vibe-game-creator/releases/latest)**

1. **Windows 10/11 x64**에서 `-setup.exe` 파일을 받아 실행합니다. Git·Node.js·Codex 데스크톱 앱을 따로 설치할 필요는 없습니다.
2. 실행기가 앱을 풀고 Python 3.12·패키지·다국어 검색 모델을 준비합니다. 기존 Codex 실행 파일이 없으면 Codex CLI도 설치합니다. 인터넷이 필요하며 첫 실행에는 몇 분 이상 걸릴 수 있습니다. 진행 내용은 설치 창에서 확인합니다.
3. 브라우저에 열린 대시보드에서 본인의 ChatGPT 계정으로 Codex에 로그인합니다. Windows 작업 권한 설정을 위한 관리자 확인 창이 나오면 완료합니다. 모델과 사용 한도는 계정의 이용 권한을 따릅니다.
4. 화면 언어를 고르고 새 프로젝트의 이름을 정한 뒤, 만들고 싶은 게임을 설명합니다.

다음부터는 바탕화면의 **Codex Vibe Game Creator** 바로가기를 사용합니다. 실행 창을 닫으면 서버도 종료되므로 작업 중에는 열어 두세요. ZIP 배포본은 압축을 풀고 `start.bat`을 실행하면 됩니다.

## 제작 흐름

- **기획:** 장르·핵심 루프·조작·화풍·분량을 대화로 구체화합니다. 선택 질문은 카드로 표시하며 직접 입력도 가능합니다.
- **기록:** 사용자 결정, AI의 제작 선택과 근거, 레퍼런스를 구분해 보관합니다. 원문은 유지합니다.
- **승인:** DB에서 만든 요약을 검토하고 `SPEC.md`를 승인한 뒤, 전체 마일스톤 계획을 승인합니다.
- **제작:** 진행 탭에서 전체 마일스톤 완료 수와 현재 마일스톤의 완료 작업 수를 확인합니다. 기록이 없으면 임의의 진행률을 표시하지 않습니다.
- **수정:** HTML 게임 미리보기, 파일 확인·수정, 레퍼런스 첨부와 변경 요청을 같은 화면에서 진행합니다.

현재는 **Codex 기반 웹게임 제작**을 지원하는 초기 배포판입니다. 사용자가 기획을 검토하고 결과를 직접 플레이하며 다듬는 과정이 필요합니다.

## 언어와 화면

**한국어·영어·일본어·중국어 간체·중국어 번체**를 지원합니다. 선택은 재실행 후에도 유지되며 AI 대화 언어는 다음 작업부터 적용됩니다. 기존 대화·결정 값·파일명·게임 내용은 자동 번역하지 않습니다. 게임 자체의 언어는 따로 결정합니다.

다크/화이트 모드, 패널 크기 드래그 조절, 접힌 패널의 가장자리 마우스 표시를 지원합니다. Enter는 전송, Shift+Enter는 줄바꿈입니다.

## 업데이트와 데이터

대시보드의 **업데이트 다운로드** 또는 Releases에서 새 버전을 받습니다. 현재 작업을 마치고 실행 창을 닫은 다음 새 설치 파일을 실행하세요. 앱은 버전별 폴더에 저장하고 바로가기를 갱신합니다. 게임 폴더·결정 기록·로그인 정보를 초기화하지 않습니다. 자동 백그라운드 업데이트는 아직 없습니다.

| 내용 | 위치 |
|---|---|
| 설치된 앱 | `%LOCALAPPDATA%/GameHarness/apps/<버전>-<빌드>/` |
| 설치판의 새 프로젝트 | `%LOCALAPPDATA%/GameHarness/GameProjects/` |
| 결정 DB·첨부·게임 파일 | 각 프로젝트 폴더 내부 |
| Python 패키지·검색 모델 | `%LOCALAPPDATA%/GameHarness/runtimes/` |
| 프로젝트 목록·대화 이력·Codex 로그인 | `%LOCALAPPDATA%/GameHarness/dashboard/` |
| 자동 설치한 Python·Codex | `%LOCALAPPDATA%/GameHarness/tools/` |

기존 사용자는 대시보드에 등록된 프로젝트 보관 경로를 계속 사용합니다. 소스/ZIP으로 처음 실행하면 기본 보관 위치는 하네스 폴더의 형제 `GameProjects/` 폴더입니다. 업데이트하려고 공용 데이터 폴더를 삭제하지 마세요. 백업은 서버 종료 후 프로젝트 폴더와 dashboard 폴더를 복사합니다. dashboard 폴더에는 인증 정보가 있으므로 공개하지 마세요.

## 연결과 문제 해결

대시보드는 `127.0.0.1`에서 실행하며, Codex는 프로젝트 폴더로 쓰기 범위를 제한한 지속 세션을 사용합니다. AI 요청은 OpenAI로 전송되며 오프라인 AI 도구는 아닙니다.

- 설치 실패: 설치 창의 마지막 메시지를 확인하고 다시 실행합니다.
- 연결 끊김: 재연결을 누릅니다. 서버가 종료됐다면 바로가기로 다시 실행하고 새로 열린 페이지를 사용합니다.
- 권한 설정 실패: 관리자 확인을 완료하거나 작업 권한 설정 재시도를 누릅니다.
- 진행도 없음: 현재 마일스톤의 진행 기록을 AI에 요청합니다. 과거 진행률을 추정하지 않습니다.
- 배포 실행 파일은 아직 코드 서명이 없습니다. 이 저장소의 Releases에서 내려받고 `SHA256SUMS.txt`로 파일을 확인할 수 있습니다.

현재 버전: **0.1.1** · [변경 이력](../CHANGELOG.md) · [유지보수·배포 안내](maintaining.md)

## 라이선스와 외부 구성요소

이 프로젝트는 [MIT 라이선스](../LICENSE)를 사용합니다. Release의 ZIP·설치 파일에는 하네스 코드와 문서가 들어갑니다. Python·Codex는 기존 설치본을 사용하거나 설치 과정에서 다운로드하고, Python 패키지와 임베딩 모델은 공용 실행 환경에 설치합니다. SQLite는 Python을 통해 사용합니다. Windows PowerShell·.NET Framework는 Windows의 실행 전제조건이며 배포 파일에 포함하지 않습니다.

| 구성요소 | 버전 / 제공처 | 라이선스 |
|---|---|---|
| Python | 3.12.10 | [PSF License Agreement](https://docs.python.org/3.12/license.html) |
| Codex CLI | 0.160.0 | [Apache-2.0](https://github.com/openai/codex/blob/rust-v0.160.0/LICENSE) |
| Semantica | 0.7.0 | [MIT](https://github.com/semantica-agi/semantica/blob/main/LICENSE) |
| SQLite | Python runtime | [Public domain](https://www.sqlite.org/copyright.html) |
| sqlite-vec | 0.1.9 | [MIT](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-MIT) / [Apache-2.0](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-APACHE) |
| FastEmbed | 0.8.1 | [Apache-2.0](https://github.com/qdrant/fastembed/blob/main/LICENSE) |
| ONNX Runtime | 1.30.0 | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | Model | [Apache-2.0](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) |

고정된 Python 패키지 60개의 라이선스와 고지 파일 위치는 [외부 구성요소 라이선스 목록](third-party-licenses.md)에 정리했습니다. 각 구성요소의 라이선스는 그대로 적용되며, 하네스의 MIT 라이선스로 대체되지 않습니다.
