# Maintaining and releasing

## Source development

Use Python 3.12 on Windows x64. `start.bat` prepares the shared runtime, then opens the dashboard. The app uses native Codex app-server; Node.js is not a runtime dependency. Setup versions are in `bootstrap.json`; package versions are pinned in `requirements-runtime.txt`.

AI-facing dashboard instructions live in `instructions/dashboard.toml`. Increment its version whenever changing the instructions. Connections pin the instruction snapshot; new connections load the changed file. Delivery records include the source hash and exact rendered text. Project instructions live in `template/`.

Interface translations live in `web/locales.json`; the Korean keys are source strings and each entry has `en`, `ja`, `zh-Hans` and `zh-Hant`. Only explicit interface text is translated. Never translate saved user quotes or decisions in place. Locale metadata in a SPEC snapshot keeps existing versions stable when the display language changes.

## Build a release

1. Update `VERSION`, `CHANGELOG.md` and the localized READMEs.
2. Run the affected tests. The record/interaction tests use disposable projects and do not perform model inference:

   ```powershell
   python -B -m unittest test_planning.PlanningTests test_dashboard.DashboardTests test_localization -v
   ```

3. Build the Windows artifacts:

   ```powershell
   python -B build_release.py
   ```

   This uses the Windows .NET Framework C# compiler, creates `dist/*-setup.exe`, a ZIP and `SHA256SUMS.txt`. `--zip-only` skips the compiler. The builder uses an explicit file allowlist, excludes personal state, and copies the end-user template as the package's root AGENTS.md. Both runtime files and resources are individually listed in `build_release.py` (`FILES` and `RESOURCE_FILES`); new release resources must be added there explicitly. Tests, fixtures, and scratch files stay in the source workspace and are not included simply because they are inside a resource folder. The installer embeds the same ZIP payload.
4. Test the setup on a clean Windows x64 environment, including first sign-in and sandbox setup. The `--extract-only <empty-folder>` executable option checks package extraction without installing dependencies or creating a session.
5. Publish a tag matching VERSION and attach those three assets to a GitHub Release. The workflow builds a **draft** release on `v*` tags; review it before publishing.

## Updating existing installations

Setup creates an app directory keyed by version and payload hash, separate from the data directories. Installing the next release updates the desktop shortcut. Existing project locations and database records remain unchanged. Close the old server before switching releases. Old app builds are not automatically removed.

Changing dependency pins creates a new shared runtime directory. Existing projects retain their runtime reference; migrations must be explicit and preserve their records. Connecting a project updates only its managed decisions.py support script, not the game files. Do not silently rewrite every existing guide when changing a template.

Do not reuse a published version number for a different release. The first release is a preview and is not code-signed.
