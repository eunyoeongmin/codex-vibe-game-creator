# Codex Vibe Game Creator

透過對話製作自己的遊戲。描述想法，與 Codex 一起完善設計，再於本機網頁工作室中製作和試玩。

[한국어](README.ko.md) · [English](../README.md) · [日本語](README.ja.md) · [简体中文](README.zh-Hans.md) · 繁體中文

這是獨立的社群專案，並非 OpenAI 官方產品。

## 下載與啟動

**[下載最新版本](https://github.com/eunyoeongmin/codex-vibe-game-creator/releases/latest)**

1. 在 **Windows 10/11 x64** 下載並執行 `-setup.exe`。不必事先安裝 Git、Node.js 或 Codex 桌面應用程式。
2. 啟動器會解壓縮應用程式並準備 Python 3.12、相依套件和多語言搜尋模型。如果找不到既有的 Codex 程式，還會安裝 Codex CLI。需要網路連線，首次執行可能需要數分鐘以上，安裝視窗會顯示進度。
3. 在瀏覽器開啟的控制台中，以自己的 ChatGPT 帳號登入 Codex。出現 Windows 沙箱權限的系統管理員確認時，請完成設定。可用模型和使用額度取決於帳號權限。
4. 選擇語言，建立專案並命名，再描述想製作的遊戲。

日後可使用桌面的 **Codex Vibe Game Creator** 捷徑啟動。工作時請保持執行視窗開啟，關閉視窗會停止本機伺服器。也可下載 ZIP，解壓縮後執行 `start.bat`。

提供遊戲存檔與遊玩起點、遊戲文字翻譯、控制變數的玩法比較、系統連動設計和各內容單元的玩法差異表。存檔需連接遊戲專用的 capture/restore 介面，可要求 AI 接入實際遊戲狀態。轉換存檔時保留原始資料。翻譯編輯遊戲使用的已註冊 JSON，檢查缺少翻譯、變數不符及目前可見 DOM 文字溢出。設計提案、使用者選擇與實作依據分別記錄，並關聯使用者及工作決定。不自動判斷樂趣或滿意度。

聲音演出管理已註冊音訊的使用情境、循環、淡入淡出、同時播放數、優先順序及語音期間的背景音降低，可試聽並要求接入實際遊戲事件。遊戲平衡透過遊戲實際計算函式比較輸入與目標範圍，保留依據和結果。比較不會修改遊戲數值，需明確要求調整後套用。

## 創作工具

右側創作工具提供：已登錄 JSON/CSV 資料的逐列編輯，包含圖片、說明和選用遊戲狀態的試玩回饋，製作檢查點儲存與還原，獨立資料夾中比較方案的執行與採用，獨立故事紀錄，以及遊戲 ZIP 匯出。

先讓 AI 登錄實際遊戲資料，再進行編輯。還原或採用方案前會儲存目前檔案，對話紀錄不回溯。AI 將故事儲存為提案，由使用者確認版本；確認不會自動修改遊戲程式碼。取得狀態需要遊戲提供 `GameCreatorFeedback()`。匯出範圍為所選 HTML 所在資料夾；引擎專案請先建置 Web 輸出。


可在靜態截圖上標記區域並請求修改、比較前後圖片，檢視有依據的資料關係，以及編輯台詞、移動、圖片、聲音、轉場和等待的演出時間軸。支援遊戲內預覽及產生可重用的執行檔案。Canvas 或引擎物件需要透過接入請求實作配接器。擷取靜態圖片不會暫停遊戲本身。

## 製作流程

預覽中的 **邊玩邊製作** 可並排顯示遊戲和編輯工具。首次請 AI 連接實際遊戲對象和狀態，然後選擇對象、記錄操作、儲存節點，並要求修改或建立修改版。可將兩個版本還原到同一儲存狀態後比較並採用。**系統關係圖** 顯示系統以及關卡、事件、獎勵和解鎖之間的關係，並區分設計、程式碼依據和實際觀察。既有遊戲也需要連接轉接器，不會自動猜測任意遊戲狀態。

- 透過對話確定類型、核心循環、操作方式、美術風格與內容規模。選擇卡片也支援自由輸入。
- 分別記錄使用者決策、AI 的製作選擇與依據、參考資料，並保留原文。
- 檢視資料庫產生的設計摘要，核准 `SPEC.md`，再核准完整的里程碑計畫。
- 在進度分頁檢視已完成的里程碑，以及目前里程碑內的工作進度。沒有紀錄時不會編造百分比。
- 在同一工作室預覽 HTML 遊戲、編輯文字檔案、附加參考資料並提出修改需求。

目前是以 **Codex 製作網頁遊戲**的早期版本。仍需要使用者審閱設計、試玩並調整成果。

## 語言與介面

支援韓文、英文、日文、簡體中文與繁體中文。語言設定會在重啟後保留，AI 對話語言從下一輪工作起生效。既有對話、決策值、檔案名稱和遊戲內容不會自動翻譯。遊戲本身的語言須另行決定。

支援深色/淺色模式、拖曳調整面板大小，以及將滑鼠移至邊緣顯示已收合的面板。Enter 傳送，Shift+Enter 換行。

## 更新與資料

透過控制台的「下載更新」或 Releases 取得新版安裝程式。請先結束目前工作並關閉執行視窗，再執行新版本。應用程式按版本分開存放並更新桌面捷徑，不會重設遊戲、決策紀錄或登入資訊。目前沒有背景自動更新。

| 內容 | 位置 |
|---|---|
| 應用程式 | `%LOCALAPPDATA%/GameHarness/apps/<version>-<build>/` |
| 安裝版的新專案 | `%LOCALAPPDATA%/GameHarness/GameProjects/` |
| 決策資料庫、參考資料、遊戲檔案 | 各專案資料夾內 |
| Python 套件與搜尋模型 | `%LOCALAPPDATA%/GameHarness/runtimes/` |
| 專案清單、對話紀錄、登入資訊 | `%LOCALAPPDATA%/GameHarness/dashboard/` |
| 自動安裝的工具 | `%LOCALAPPDATA%/GameHarness/tools/` |

既有的專案存放位置會保留。首次使用原始碼/ZIP 版本時，預設在應用程式的同層 `GameProjects/` 資料夾建立專案。請勿為了更新而刪除共用資料。備份時先停止伺服器，再複製專案資料夾和 dashboard 資料夾；後者包含驗證資訊，請勿公開。

## 連線與問題排除

控制台僅監聽 `127.0.0.1`，Codex 的寫入範圍限制在專案內。AI 請求會傳送至 OpenAI，因此不是離線 AI 應用程式。

安裝失敗時，請查看安裝視窗最後一則訊息後重試。連線中斷時可按「重新連線」；若伺服器已結束，請由捷徑重新啟動並使用新頁面。權限設定失敗時，請完成系統管理員確認或重試設定。

目前發行的執行檔尚未進行程式碼簽章。請從本儲存庫的 Releases 下載，可使用 `SHA256SUMS.txt` 核對檔案。

版本 **0.1.2** · [更新紀錄](../CHANGELOG.md) · [維護與發行](maintaining.md)

## 授權條款與第三方元件

本專案採用 [MIT 授權條款](../LICENSE)。Release 的 ZIP 與安裝程式包含本工具的程式碼和文件。Python 與 Codex 使用既有安裝，或在安裝過程中下載；Python 套件與嵌入模型安裝至共用執行環境。SQLite 透過 Python 使用。Windows PowerShell 與 .NET Framework 是系統相依元件，不包含在發行檔案中。

| 元件 | 版本 / 來源 | 授權條款 |
|---|---|---|
| Python | 3.12.10 | [PSF License Agreement](https://docs.python.org/3.12/license.html) |
| Codex CLI | 0.160.0 | [Apache-2.0](https://github.com/openai/codex/blob/rust-v0.160.0/LICENSE) |
| Semantica | 0.7.0 | [MIT](https://github.com/semantica-agi/semantica/blob/main/LICENSE) |
| SQLite | Python runtime | [Public domain](https://www.sqlite.org/copyright.html) |
| sqlite-vec | 0.1.9 | [MIT](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-MIT) / [Apache-2.0](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-APACHE) |
| FastEmbed | 0.8.1 | [Apache-2.0](https://github.com/qdrant/fastembed/blob/main/LICENSE) |
| ONNX Runtime | 1.30.0 | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | Model | [Apache-2.0](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) |

固定版本的 60 個 Python 套件之授權條款與聲明檔案位置，請見[第三方元件授權清單](third-party-licenses.md)。各元件保留各自的授權條款，本工具的 MIT 授權條款不會取代它們。
