# Video Critique Assistant Plan

## Goals
- Add a new "Video Critique Assistant" page under AI Chat Assistant in unified-ui-react.
- Provide a chat UI that mirrors the existing AI Chat Assistant (same styles/components).
- Provide a dashboard view with summary metrics + lists using dummy data until backend is ready.
- Keep all new feature work in separate files (minimize changes to existing pages).

## Files to Access (Read/Write)
- Read: `Old Code Archive/video-critique/README.md` (feature context)
- Read: `Old Code Archive/video-critique/orphan/node-dashboard/README.md` (dashboard data shape)
- Update: `src/routes/AppRoutes.jsx` (add Video Critique route)
- Update: `src/shell/AppShell.jsx` (add sidebar entry under AI Chat Assistant)
- Add: `src/screens/tools/video-critique/VideoCritiqueAssistantPage.jsx` (chat UI + dashboard tabs)
- Add: `src/screens/tools/video-critique/VideoCritiqueChatPanel.jsx` (chat view; copied logic)
- Add: `src/screens/tools/video-critique/VideoCritiqueDashboard.jsx` (dashboard UI)
- Add: `src/api/videoCritique.js` (API wrapper; uses mock provider for now)
- Add: `src/api/videoCritiqueMock.js` (dummy data + fake streaming)
- Update: `src/api/index.js` (export videoCritiqueApi)

## Step-by-Step Plan
1. Review the video-critique README + dashboard docs to align core entities and metrics.
2. Create mock API module (`videoCritiqueMock.js`) returning dashboard data + fake streaming chat events.
3. Add a new API wrapper (`videoCritique.js`) that delegates to the mock provider for now.
4. Build Video Critique chat panel using the same UI patterns as `ChatPage.jsx`.
5. Build the dashboard panel using existing UI primitives (`Card`, `SoftCard`, `Button`).
6. Wire a new route under `/app/video-critique` and add a sidebar entry beneath AI Chat Assistant.
7. Verify the new page loads, chat works with dummy responses, dashboard renders data.

## Backend TODO Endpoints (Chat Parity)
- `POST /api/chat/message/stream`
  - Request: `{ message, session_id?, file_ids? }`
  - Response: SSE `data:` events with `{ type, content?, status?, files?, actions?, session_id?, message_id? }`
  - Types expected: `status`, `delta`, `text_done`, `tool_call`, `files`, `actions`, `done`, `error`
- `POST /api/chat/files/upload`
  - Request: `multipart/form-data` (`file`)
  - Response: `{ file_id, filename, file_url }`
- `POST /api/chat/upload`
  - Request: `multipart/form-data` (`file`, `message?`, `session_id?`)
  - Response: `{ success, file_id, file_url?, type, response?, message?, session_id }`
- `POST /api/videos/upload`
  - Request: `multipart/form-data` (`file`, `task_number`)
  - Response: `{ success, file_id, workflow_id, version, message }`
- `POST /api/chat/action`
  - Request: `{ action_id, workflow_id }`
  - Response: `{ success, message, requires_form, form_type, workflow_id }`
- `POST /api/chat/form`
  - Request: `{ form_type, workflow_id, category?, reason? }`
  - Response: `{ success, message }`
- `GET /api/chat/forms/{form_type}`
  - Response: `{ title, submit_text, fields: [{ id, label, type, required, options?, placeholder? }] }`
- `GET /api/chat/history`
  - Response: `{ messages: [{ id, role, content, files?, actions? }], session_id, message_count, last_updated }`
- `POST /api/chat/command`
  - Request: `{ command, args?, session_id? }`
  - Response: `{ success, command, response?, error?, session_id }`
- `GET /api/chat/workflows/pending`
  - Response: `{ count, workflows: [{ workflow_id, task_number, folder_name, status, created_at, reviewer_approved, hos_approved }] }`
- `GET /api/chat/workflows/{workflow_id}`
  - Response: `{ workflow_id, task_number, status, reviewer_approved, hos_approved, created_at, updated_at }`

## Chat UI Payload Expectations
- Assistant messages can include `actions: [{ action_id, label, workflow_id, variant?, url? }]` to render buttons.
- File payloads in `files` should include `{ file_id, filename, file_url?, url?, comment?, pdf_filename? }`.

## Dashboard Endpoints
- `GET /api/dashboard?mode=&period=`
  - Response: `{ summary, tasks, reviewer, pie, summary_videographers, videographers }`
- `GET /api/dashboard/stats`
- `GET /api/dashboard/workload`
- `GET /api/dashboard/upcoming-shoots`
- `GET /api/dashboard/by-status`
- `GET /api/dashboard/by-location`
- `GET /api/dashboard/by-videographer`

## Optional Workflow Endpoints (Direct Actions)
- `POST /api/videos/approve/reviewer` -> `{ workflow_id }` => `{ success, message, next_stage }`
- `POST /api/videos/reject/reviewer` -> `{ workflow_id, reason?, category? }` => `{ success, message }`
- `POST /api/videos/approve/hos` -> `{ workflow_id }` => `{ success, message, next_stage }`
- `POST /api/videos/return/hos` -> `{ workflow_id, reason?, category? }` => `{ success, message }`
