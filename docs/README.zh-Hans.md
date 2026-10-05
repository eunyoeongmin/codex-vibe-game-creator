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

## 制作流程

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

版本 **0.1.1** · [更新日志](../CHANGELOG.md) · [维护与发布](maintaining.md)

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
