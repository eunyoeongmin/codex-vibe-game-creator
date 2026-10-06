# Changelog

## 0.1.2

- Display images in Codex replies and image-generation results.
- Add fullscreen game previews, complete preview URLs and address copying.
- Add model speed selection and fix Shift+Enter in choice-card text input.
- Add image, sound and code-art asset management, previews, revision history and targeted AI modification requests.
- Track reference research sources, user statements, AI interpretations, application plans and implementation locations; preserve revisions and flag changed evidence.
- Link references to user/work decisions and asset versions, with a readable dashboard history.
- Add draft developer, art, verification, game designer and reference roles; separate their instructions from orchestrator workflow.
- Clarify design hypotheses, delegated choices, system relationships, interface feedback and unused-result handoff.
- Package only explicitly listed application files; exclude local tests, fixtures and development data.
- Preserve existing project data. Legacy assets still need registration, and missing historical research is not inferred. Existing customized role guides are not overwritten.

## 0.1.1

- Attach files by drag and drop, or paste copied images into the message input.
- Preview attached images before sending and display sent images when reopening conversations.
- Load the latest 30 conversation entries first, then load older entries on upward scroll without moving the reading position.
- Reconstruct historical replies without replaying individual streaming fragments; preserve original event logs.
- Show live Codex activity from app-server events, including reply writing, commands, file operations and search.
- Fix activity visibility when sending ordinary messages while question cards remain open.
- Add the MIT license, third-party license tables in all five READMEs, and an inventory of all 60 pinned Python packages.

## 0.1.0

First packaged preview of Codex Vibe Game Creator.

- Local Codex conversations, project isolation, choice cards, file editing and game preview.
- Separate user/work decisions and references, backed by SQLite and Semantica.
- Database-derived design summaries, versioned SPEC files and milestone/task progress.
- Korean, English, Japanese, Simplified Chinese and Traditional Chinese interface and conversation settings.
- Light/dark themes, resizable panels and edge-hover panel reveal.
- Windows setup executable and ZIP, dependency bootstrap, versioned app folders and a desktop shortcut.
- Instruction source and delivery tracing. Existing game data is preserved across app updates.
