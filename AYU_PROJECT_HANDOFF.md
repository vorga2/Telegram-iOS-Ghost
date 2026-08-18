# AyuGram iOS v0.3 — project handoff

This file is the durable handoff for continuing the project in a fresh ChatGPT conversation.

## Working repo / branch / PR
- Repo: `vorga2/Telegram-iOS-Ghost`
- Active development branch: `ayu-v03-finish-staging`
- PR: #16, title `CI: build Ayu v0.3 IPA finish staging`, base `main`
- Telegram upstream pin: `6ad963e5b62d354da79040f388ae2b9132fb17b8`
- Work is patcher-based: GitHub Actions checks out pinned Telegram-iOS and applies Python patchers.

## User workflow / style
- Russian.
- Wants direct, concrete work, not manual code inspection/editing.
- Prefer actual GitHub edits and ready fixes.
- User asked to work feature-by-feature: `1`, then `2`, then `3`, etc. Do one focused chunk and report result.
- Avoid long explanations and repeated clarifying questions when the next step is obvious.

## Build workflow
Workflow: `.github/workflows/pr-verify.yml`
- macOS 26, Xcode 26.2.
- Fixed dev build number: `3000`.
- Persistent caches:
  - `~/telegram-bazel-cache`
  - `~/telegram-bazel-user-root`
- `cancel-in-progress: true`.
- Fast compile-check before full IPA for Ayu-touched targets.
- Full IPA target is `release_arm64`.
- Earlier compile blocker `ayuUsesTelegramTheme` unused Swift local was fixed with `apply_ayu_deleted_visual_compile_fix.py`; it is run again at the end of patch application to prevent later patchers reintroducing it.

## Major implemented features

### Ghost mode / settings
- Telegram settings contains `Настройки AyuGram`.
- Categories: `Режим Призрака`, `Кастомизация`, `Шпион`.
- Category navigation lifetime bug was fixed: the category handlers retain the weak controller box correctly.
- Ghost section includes `Режим призрака X/5`, read messages/stories, online, typing, automatic offline, `Читать при действиях`, `Использовать отложку`.
- No `Отправлять без звука`.

### Deleted messages
- Remote deletes are preserved and updated in realtime.
- Deleted-message archive in Files under the app Documents root (`На iPhone/AyuGram/...`), with `Deleted/deleted.sqlite`, saved photo/voice/video-message folders.
- Deleted whole-item translucency toggle exists (`Полупрозрачные удаленки`, default ON).
- Viewer uses stock Telegram chat rendering and shows preserved messages at full opacity.
- Burn behavior persists and shows flame marker near timestamp after burn.
- Deleted marker customization currently uses blank / 👀 / ❌; user explicitly asked to RETURN 🗑 to the marker choices. This is still pending.

### Manual Read
- Context-menu `Прочитать` uses `ayuReadMessageThroughGhost`.
- It advances local read state and directly sends server read requests (`messages.readHistory`, `channels.readHistory`, secret chat read history) to avoid Ghost synchronization races.

### Spy — settings
- `Сохранять удалённые сообщения`.
- `Сохранять историю правок`.
- `Сохранять дату прочтения`.
- Read-date description starts with: `Локально сохраняет данные о чтении сообщений. Будет использоваться, если Telegram не предоставит дату чтения`.

### Spy — Details
- Long-press Telegram ContextUI action `Детали`.
- Nested Telegram context menu, not ActionSheet / half-screen.
- Top item `Назад`, separator, then detail rows.
- Base fields: ID, date.
- Deleted messages can show deletion date.
- Media details include MIME, size, resolution, duration, average bitrate where metadata permits.
- Current media-accuracy weaknesses still worth refining later: photo MIME is hard-coded jpeg; sticker/custom-emoji MIME handling may not exactly match desired `application/x-tgsticker`; bitrate is computed average from size/duration.

## Spy edit history — feature 2, latest state
The user asked that edit history be saved for PMs, groups, supergroups and channels, then opened as a chat-like screen with avatar/name/status header and date separators.

Relevant patcher: `apply_ayu_spy_edit_history.py`.

Latest important commits:
- `a0592b2ee0dee8a311ae44ced417e902fd7788df` — incoming + own PM/group/channel edit history plus chat-style viewer.

What it does:
- Old v0.3 hook in `addUpdates()` was wrong because normal live updates come through `addUpdateGroups()`.
- New hook captures `.updateEditMessage` and `.updateEditChannelMessage` before Postbox replacement.
- Saves previous text only when the new text differs.
- Uses Telegram edit date when available.
- Also patches `RequestEditMessage.swift` for edits made by this same client.
- SQLite table `edit_history`, indexed by peer/message/timestamp.
- Query helper `ayuSpyEditHistory`.
- Long-press context action `История правок` only appears if revisions exist.
- Payload: `payload/AyuEditHistoryController.swift`.
- Viewer is built on stock Telegram custom-chat renderer; versions appear as messages with text/time and Telegram date separators.
- Intended header: avatar + author/channel name + presence/last seen where available.
- Historical revisions missed by old builds cannot be reconstructed retroactively.

## Current active task — feature 3: read dates
This was being implemented when the handoff was written. Continue from here first.

### Regular read-date patcher
File: `apply_ayu_spy_read_dates.py`
Latest commit: `4040affe7a392264e96f21dde9c10862927802ba`
Marker upgraded to `AYU_SPY_READ_DATES_v0_4` (keeps v0.3 compatibility string).

Changes already made:
- Previously all `CloudChannel` peers were excluded, which incorrectly excluded supergroups.
- Now private chats + basic groups + supergroups are intended to be saved, while broadcast channels are excluded.
- `.updateReadHistoryOutbox` uses `updatesDate ?? serverTime`.
- `.updateReadChannelOutbox` is now handled; the patch resolves `TelegramChannel.info` through Postbox and stores only `.group`, rejecting broadcasts.
- Storage remains max-read boundary based (`read_receipts`) for low disk/CPU overhead.

### Content-read patcher
File: `apply_ayu_spy_content_read_dates.py`
Latest commit: `0c8737465e727bed3b005e1803753b88dd74a769`
Marker upgraded to `AYU_SPY_CONTENT_READ_DATES_v0_4`.

Changes already made:
- Server-aware timestamp preference: Telegram-provided date / `serverTime`, local clock only fallback.
- New peer-qualified table `content_read_receipts_v2(peer_id, message_id, read_at)` to avoid ambiguity.
- Keeps legacy `content_read_receipts` for old test-build compatibility.
- Generic `.updateReadMessagesContents` resolves global IDs to MessageIds and stores v2 rows.
- `.updateChannelReadMessagesContents` is hooked and resolves supergroup vs broadcast by `TelegramChannel.info`; only groups are saved.
- Content-read Details should use only true content-consumed timestamp, NOT generic regular message-read timestamp.

### IMPORTANT: feature 3 is NOT fully finished yet
Before calling feature 3 done, do these focused checks/fixes:
1. Reconcile `apply_ayu_spy_content_read_dates.py` with actual pinned `AccountStateManagementUtils.swift` scopes. Verify every injected use of `serverTime` occurs inside a function where `serverTime` is in scope. The main update switch in `finalStateWithUpdatesAndServerTime(...)` has it, but verify any repeated anchors in alternate paths before build.
2. `apply_ayu_spy_details.py` still creates the old regular-read query with `messageId.peerId.namespace != Namespaces.Peer.CloudChannel`; content-read patcher currently tries to rewrite it. Verify the exact anchor works after patcher order: read_dates -> details -> content_read_dates.
3. Update `ci_verify_hotfixes.py`: it still expects the old behavior string `peerId.namespace != Namespaces.Peer.CloudChannel`, so verifier must be changed to validate supergroup support + broadcast exclusion instead.
4. Verifier should check `updateReadChannelOutbox`, channel.info group filtering, `content_read_receipts_v2`, and server-aware timestamp paths.
5. Static-check patcher anchors before launching a long IPA build.
6. Do not claim compile success until GitHub Actions has actually passed.

## Remaining known work after feature 3
- Return 🗑 to deleted marker picker (user explicitly requested this).
- Exact `Читать при действиях` semantics for replies/reactions are not fully proven; send and content consume are guarded, but reply/reaction paths need focused audit/hook.
- Verify `Использовать отложку` is fully wired semantically, not only shown in settings.
- Details media accuracy cleanup (photo/sticker MIME and bitrate semantics).
- Final verifier/pipeline audit and final IPA build.

## Prior CI/build failures worth remembering
1. Swift warnings-as-errors failure in `ChatMessageBubbleItemNode.swift`:
   `immutable value 'ayuUsesTelegramTheme' was never used`.
   Fixed by compile-fix patcher and final cleanup application.
2. Verifier later failed because it searched for the literal name in a comment even though code was fixed; verifier/comment were corrected.
3. Earlier deleted archive patcher failure:
   `deleted archive event hook: expected 1 anchor, found 2`.
   Fixed by making raw/final deletion loops structurally distinct.

## Performance intent
- Keep hot paths event-driven.
- No polling / chat-history scans.
- SQLite writes on serial background queues.
- Indexed lookups only when opening Details/history.
- Expected steady-state FPS impact should be very small; this is an engineering estimate, not a benchmark.

## How to continue in a fresh chat
Tell ChatGPT: `Продолжаем AyuGram iOS, прочитай AYU_PROJECT_HANDOFF.md из ветки ayu-v03-finish-staging и продолжай с feature 3.`
