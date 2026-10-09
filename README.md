# Codex Vibe Game Creator

Create games through conversation with Codex. Describe an idea, shape the design together, then build and play in a local web workspace.

**[한국어](docs/README.ko.md) · English · [日本語](docs/README.ja.md) · [简体中文](docs/README.zh-Hans.md) · [繁體中文](docs/README.zh-Hant.md)**

An independent community project. Not an official OpenAI product.

## Download and start

**[Download the latest release](https://github.com/eunyoeongmin/codex-vibe-game-creator/releases/latest)**

1. On **64-bit Windows 10/11 (x64)**, download the `-setup.exe` release asset and run it. Git, Node.js and a separate Codex desktop installation are not required.
2. The launcher extracts the app, prepares Python 3.12, installs the Python packages and multilingual search model, and installs Codex CLI when no existing executable is found. Internet access is required. The first run can take several minutes; the setup window shows progress.
3. In the browser dashboard, sign in to **Codex with your own ChatGPT account**. Complete the Windows administrator prompt for project sandbox setup when shown. Model availability and usage limits depend on your account.
4. Choose a language, create a project, give it a name, and describe the game you want to make.

Later, use the **Codex Vibe Game Creator** desktop shortcut. Keep the launcher/server window open while working; closing it stops the local server. The release ZIP is an alternative: extract it and run `start.bat`.

Play tools include versioned game saves and play points, a game-string translation editor, controlled playable comparisons, system-connection plans and per-content progression tables. Saves require a game-specific capture/restore adapter; AI connection requests wire it to the current game. Older save originals are preserved during migration. Localization edits actual registered JSON catalogs, checks missing translations and variables, and reports overflow for visible marked DOM strings only. Design proposals, user selections and implementation evidence stay distinct; selected designs link to user decisions and implemented changes to work decisions. These tools do not automatically judge fun or user satisfaction.

Sound direction adds event-linked music, effects, ambience and voice with looping, fades, overlap limits, priorities and music ducking. Audition registered assets and request integration with actual game events. Game balance compares user-selected inputs and target ranges through registered functions from the game, preserving calculation evidence and results. Comparisons do not change game values; apply changes through an explicit adjustment request.

## Creation tools

The right-hand **Creation tools** tab includes:

- **Content editor:** ask AI to register the game's actual JSON/CSV data, then edit individual rows or request a targeted change. IDs stay fixed; field types, ranges and references are checked.
- **Play feedback:** capture a selected screen or attach an image, save a note, then send it to AI. Game state is optional and requires the game's `GameCreatorFeedback()` hook. Capture and state timestamps remain separate.
- **Checkpoints:** save game files and records; restoring first preserves the current version. Conversation history and the shared runtime are not rewound.
- **Alternatives:** copy a playable version, request changes to that copy, run both versions side by side and choose one. Adoption is refused if the original has changed in the meantime.
- **Story workspace:** keep characters, events, branches, conditions and game effects separate. AI saves proposals; the user confirms versions. Story confirmation does not automatically change game code.
- **Export game:** choose the HTML entry point and download a game ZIP with launch instructions. For engine projects, build web output first. Files outside the selected HTML folder and remote services are not bundled.


Mark regions on a captured still image to request precise changes and compare before/after images. Data relationships show registered links and their evidence separately from text matches in code. Sequence timelines support dialogue, movement, images, sound, transitions and waits; edit their order and timing, preview them in the game, and publish reusable runtime/data files. Canvas and engine objects require an adapter through the integration request. Capturing a still image does not pause the running game.

## From idea to game

In the preview, **Create while playing** opens the game beside its editing controls. Ask AI to connect the game's real targets and state once; then select a target, record actions, save a point, and request an edit or create an alternative. Compare both versions from the saved state before adopting. **System map** shows system and stage/event/reward/unlock links, with separate design, code evidence and observed execution. Existing games need these adapters connected; arbitrary game state is not inferred automatically.

- **Plan through conversation.** The assistant helps with genre, core loop, controls, visual direction and a concrete content scope. Questions appear as selectable cards with a free-text answer option.
- **Keep the reasoning.** User decisions, AI work choices and references are recorded separately. Original messages remain intact.
- **Approve the design.** Review the database-generated summary and approve `SPEC.md`, then approve the milestone plan before implementation.
- **Follow production.** The progress tab shows completed milestones and recorded task progress inside the current milestone. It does not invent a percentage when no progress has been recorded.
- **Play and refine.** Preview HTML games, inspect or edit text files, attach references, and ask for changes in the same workspace.

The current release focuses on **web games using Codex**. It is a work in progress; creating a game still involves reviewing the design and trying the result.

## Languages and layout

The language menu supports **Korean, English, Japanese, Simplified Chinese and Traditional Chinese**. The setting survives a restart and applies to subsequent AI turns. Existing conversations, decision values, filenames and game content are not automatically translated. The language of the game itself is a separate design choice.

Light/dark modes, draggable panel sizes and edge-hover panels are available. Press Enter to send a message; Shift+Enter inserts a line break.

## Updates and your data

Use **Download updates** in the dashboard or visit Releases. Finish the current task and close the running server, then run the new setup executable. It creates a separate application build folder and updates the desktop shortcut; it does not replace your game folders or reset your records. Automatic background updates are not implemented.

| Contents | Location |
|---|---|
| Installed app builds | `%LOCALAPPDATA%/GameHarness/apps/<version>-<build>/` |
| New installed-app projects | `%LOCALAPPDATA%/GameHarness/GameProjects/` |
| Project decisions, references and game files | Inside each project folder |
| Shared Python packages and search model | `%LOCALAPPDATA%/GameHarness/runtimes/` |
| Dashboard history, project registry and Codex sign-in | `%LOCALAPPDATA%/GameHarness/dashboard/` |
| Managed Python/Codex tools, if installed | `%LOCALAPPDATA%/GameHarness/tools/` |

Existing installations retain the project location already registered in the dashboard. When using a source/ZIP checkout for the first time, new projects default to the sibling `GameProjects/` folder. Do not delete the shared data folder to update the app. To back up, close the server and copy your project folders plus the dashboard folder; treat the latter as private because it contains authentication data.

## Local operation

The dashboard listens on **127.0.0.1** with a per-run access token. Codex uses a persistent `app-server` conversation scoped to the selected project. Out-of-project write approvals are denied. AI requests go to OpenAI; Python packages, the search model and Codex may be downloaded during setup. This is not an offline AI application.

## Troubleshooting

- **Setup failed:** read the last message in the setup window and run it again. Working projects are kept separately.
- **Connection interrupted:** use Reconnect. If the server has stopped, open the desktop shortcut again and use the newly opened page.
- **Windows permissions:** finish the administrator prompt. Use Retry permission setup if setup was canceled or failed.
- **No milestone percentage:** ask the assistant to record the active milestone's progress. Old records do not have fabricated progress values.
- **Installation warnings:** release executables are currently unsigned. Download from this repository's Releases page; checksums are included in `SHA256SUMS.txt`.

## Development and releases

See [Maintaining and releasing](docs/maintaining.md). Version: **0.1.2**. Changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the [MIT License](LICENSE). Third-party dependencies retain their own licenses.

### Third-party software

The release ZIP and setup executable contain the harness code and documentation. Python and Codex are reused when available or downloaded during setup; Python packages and the embedding model are installed into the shared runtime. SQLite is provided through Python. Windows PowerShell and .NET Framework are system prerequisites, not bundled programs.

| Component | Version / source | License |
|---|---|---|
| Python | 3.12.10 | [PSF License Agreement](https://docs.python.org/3.12/license.html) |
| Codex CLI | 0.160.0 | [Apache-2.0](https://github.com/openai/codex/blob/rust-v0.160.0/LICENSE) |
| Semantica | 0.7.0 | [MIT](https://github.com/semantica-agi/semantica/blob/main/LICENSE) |
| SQLite | Python runtime | [Public domain](https://www.sqlite.org/copyright.html) |
| sqlite-vec | 0.1.9 | [MIT](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-MIT) / [Apache-2.0](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-APACHE) |
| FastEmbed | 0.8.1 | [Apache-2.0](https://github.com/qdrant/fastembed/blob/main/LICENSE) |
| ONNX Runtime | 1.30.0 | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | Model | [Apache-2.0](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) |

The complete list of 60 pinned Python packages, declared licenses and notice locations is in [Third-party licenses](docs/third-party-licenses.md). These components retain their own licenses; the harness MIT license does not replace them.
