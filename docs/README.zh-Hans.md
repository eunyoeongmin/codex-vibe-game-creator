# Codex Vibe Game Creator

通过对话制作自己的游戏。描述想法，与 Codex 一起完善设计，然后在本地网页工作室中制作和试玩。

[한국어](README.ko.md) · [English](../README.md) · [日本語](README.ja.md) · 简体中文 · [繁體中文](README.zh-Hant.md)

这是独立的社区项目，并非 OpenAI 官方产品。

## 下载与启动

**[下载最新版本](https://github.com/eunyoeongmin/codex-vibe-game-creator/releases/latest)**

1. 在 **Windows 10/11 x64** 上下载并运行 `-setup.exe`。无需预先安装 Git、Node.js 或 Codex 桌面应用。
2. 启动器会解压应用并准备 Python 3.12、依赖包和多语言搜索模型。如果找不到已有的 Codex 程序，还会安装 Codex CLI。需要联网，首次运行可能需要数分钟以上，安装窗口会显示进度。
3. 在浏览器打开的控制台中，使用自己的 ChatGPT 账户登录 Codex。出现 Windows 沙盒权限的管理员确认时，请完成设置。模型和使用限额取决于账户权限。
4. 选择语言，新建项目并命名，然后描述你想制作的游戏。

以后可使用桌面的 **Codex Vibe Game Creator** 快捷方式启动。工作期间请保持运行窗口开启，关闭它会停止本地服务器。也可以下载 ZIP，解压后运行 `start.bat`。

提供游戏存档与游玩起点、游戏文本翻译、控制变量的玩法比较、系统联动设计和各内容单元的玩法差异表。存档需连接游戏专用的 capture/restore 适配器，可请求 AI 接入实际游戏状态。转换存档时保留原始数据。翻译编辑游戏使用的已注册 JSON，检查缺失翻译、变量不匹配及当前可见 DOM 文本溢出。设计提案、用户选择与实现依据分别记录，并关联用户及工作决定。不自动判断乐趣或满意度。

声音演出管理已注册音频的使用场景、循环、淡入淡出、同时播放数、优先级及语音期间的背景音降低，可试听并请求接入实际游戏事件。游戏平衡通过游戏实际计算函数比较输入与目标范围，保留依据和结果。比较不会修改游戏数值，需明确请求调整后应用。

## 创作工具

右侧创作工具提供：已注册 JSON/CSV 数据的逐行编辑，包含图片、说明和可选游戏状态的试玩反馈，制作检查点保存与恢复，独立文件夹中对比方案的运行与采用，独立故事记录，以及游戏 ZIP 导出。

先让 AI 注册实际游戏数据，再进行编辑。恢复或采用方案前会保存当前文件，对话历史不回退。AI 将故事保存为提案，用户确认版本；确认不会自动修改游戏代码。采集状态需要游戏提供 `GameCreatorFeedback()`。导出范围为所选 HTML 所在文件夹；引擎项目请先构建 Web 输出。


可在静态截图上标记区域并请求修改、比较前后图片，查看有依据的数据关系，以及编辑台词、移动、图片、声音、转场和等待的演出时间轴。支持游戏内预览和生成可复用的运行文件。Canvas 或引擎对象需要通过接入请求实现适配器。截取静态图片不会暂停游戏本身。

## 制作流程

预览中的 **边玩边制作** 可并排显示游戏和编辑工具。首次请 AI 连接实际游戏对象和状态，然后选择对象、记录操作、保存节点，并请求修改或创建修改版。可将两个版本恢复到同一保存状态后比较并采用。**系统关系图** 展示系统以及关卡、事件、奖励和解锁之间的关系，并区分设计、代码依据和实际观察。已有游戏也需要连接适配器，不会自动猜测任意游戏状态。

- 通过对话明确类型、核心循环、操作方式、美术风格和内容规模。选择卡片也支持自由输入。
- 分别记录用户决策、AI 的制作选择及依据、参考资料，并保留原文。
- 查看数据库生成的设计摘要，批准 `SPEC.md`，然后批准完整的里程碑计划。
- 在进度标签中查看已完成的里程碑，以及当前里程碑内的任务进度。没有记录时不会编造百分比。
- 在同一工作室中预览 HTML 游戏、编辑文本文件、附加参考资料并提出修改要求。

当前是以 **Codex 制作网页游戏**的早期版本。仍需要用户审核设计、试玩并调整结果。

## 语言与界面

支持韩语、英语、日语、简体中文和繁体中文。语言设置在重启后保留，AI 对话语言从下一轮工作开始生效。既有对话、决策值、文件名和游戏内容不会自动翻译。游戏本身使用什么语言，需要单独决定。

支持深色/浅色模式、拖动调整面板大小、将鼠标移至边缘显示已收起的面板。Enter 发送，Shift+Enter 换行。

## 更新与数据

通过控制台的“下载更新”或 Releases 获取新版安装程序。先结束当前工作并关闭运行窗口，再执行新版本。应用按版本分开存放并更新桌面快捷方式，不会重置游戏、决策记录或登录信息。尚未实现后台自动更新。

| 内容 | 位置 |
|---|---|
| 应用程序 | `%LOCALAPPDATA%/GameHarness/apps/<version>-<build>/` |
| 安装版的新项目 | `%LOCALAPPDATA%/GameHarness/GameProjects/` |
| 决策数据库、参考资料、游戏文件 | 各项目文件夹内 |
| Python 依赖与搜索模型 | `%LOCALAPPDATA%/GameHarness/runtimes/` |
| 项目列表、对话历史、登录信息 | `%LOCALAPPDATA%/GameHarness/dashboard/` |
| 自动安装的工具 | `%LOCALAPPDATA%/GameHarness/tools/` |

已有的项目存放位置会保留。首次使用源码/ZIP 版本时，默认在应用的同级 `GameProjects/` 文件夹创建项目。不要为了更新删除共享数据。备份时先停止服务器，再复制项目文件夹和 dashboard 文件夹；后者包含认证信息，请勿公开。

## 连接与故障处理

控制台仅监听 `127.0.0.1`，Codex 的写入范围限制在项目内。AI 请求发送至 OpenAI，因此不是离线 AI 应用。

安装失败时，查看安装窗口最后一条消息后重试。连接中断时点击“重新连接”；如果服务器已退出，请使用快捷方式重新启动并打开新页面。权限设置失败时，请完成管理员确认或重试权限设置。

当前发行的可执行文件尚未进行代码签名。请从本仓库 Releases 下载，可使用 `SHA256SUMS.txt` 核对文件。

版本 **0.1.2** · [更新日志](../CHANGELOG.md) · [维护与发布](maintaining.md)

## 许可证与第三方组件

本项目采用 [MIT 许可证](../LICENSE)。Release 的 ZIP 和安装程序包含本工具的代码与文档。Python 和 Codex 使用已有安装，或在安装过程中下载；Python 软件包和嵌入模型安装到共享运行环境。SQLite 通过 Python 使用。Windows PowerShell 和 .NET Framework 是系统依赖，不包含在发行文件中。

| 组件 | 版本 / 来源 | 许可证 |
|---|---|---|
| Python | 3.12.10 | [PSF License Agreement](https://docs.python.org/3.12/license.html) |
| Codex CLI | 0.160.0 | [Apache-2.0](https://github.com/openai/codex/blob/rust-v0.160.0/LICENSE) |
| Semantica | 0.7.0 | [MIT](https://github.com/semantica-agi/semantica/blob/main/LICENSE) |
| SQLite | Python runtime | [Public domain](https://www.sqlite.org/copyright.html) |
| sqlite-vec | 0.1.9 | [MIT](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-MIT) / [Apache-2.0](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-APACHE) |
| FastEmbed | 0.8.1 | [Apache-2.0](https://github.com/qdrant/fastembed/blob/main/LICENSE) |
| ONNX Runtime | 1.30.0 | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | Model | [Apache-2.0](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) |

固定版本的 60 个 Python 软件包的许可证及声明文件位置见[第三方组件许可证清单](third-party-licenses.md)。各组件保留各自的许可证，本工具的 MIT 许可证不会替代它们。
