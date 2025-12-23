# Legacy → New mapping
- `Old Code Archive/js/api.js` → `src/api/http.js`, `src/api/*` wrappers (sales/base/admin/modules/templates/proposals/bo/mockup/files/chat).
- `Old Code Archive/js/auth.js` → `src/state/auth.jsx`, login/callback screens, `routes/ProtectedRoute` (Supabase Azure OAuth, dev-mode email/password, 401 logout event).
- `Old Code Archive/js/chat.js` → `src/screens/tools/ChatPage.jsx`, `src/api/chat.js`, `src/api/files.js` (history load, SSE stream, uploads, attachments, 5-line input).
- `Old Code Archive/js/mockup.js` → `src/screens/tools/MockupPage.jsx`, `src/api/mockup.js` (generate + setup flow), permissions via `hasPermission('sales:mockups:setup')`.
- `Old Code Archive/js/proposals.js` references (via sidebar) → `src/screens/tools/ProposalsPage.jsx`, `src/api/proposals.js`.
- `Old Code Archive/js/modules.js` → `src/api/modules.js`, module/tool switching in `src/shell/AppShell.jsx`.
- `Old Code Archive/js/sidebar.js` → tool activation + admin visibility inside `AppShell`.
- `Old Code Archive/js/admin.js` → `src/screens/tools/AdminPage.jsx`, `src/api/admin.js` (users/profiles/permission-sets/teams/sharing-rules/invites/api-keys).
- `Old Code Archive/index.html` → layout/landing visuals now under `src/screens/LandingPage.jsx` and shared UI components; preserve structure/styles.

# Endpoint contracts (same-origin `/api/...`)
- Base auth: `GET /api/base/auth/session`; `GET /api/base/auth/me` → `{id,email,name?,profile_name|profile,permissions[],roles?}`; `POST /api/base/auth/validate-invite {token,email}` → `{profile_name}`; `POST /api/base/auth/consume-invite {token,email,user_id|supabase_user_id,name,profile_name?}`; 403 may include `{requiresLogout:true, code:'USER_PENDING_APPROVAL'|'USER_REMOVED', error}`.
- Invites: `GET /api/base/auth/invites?include_used=` → `{invites:[{id,email,profile_name,token,expires_at,is_used,is_revoked}]}`; `POST /api/base/auth/invites` (email, profile_name, expires_at?); `DELETE /api/base/auth/invites/:id`.
- Sales/templates: `GET /api/sales/templates`, `GET /api/sales/templates/:locationKey`, `POST /api/sales/templates` (JSON), `DELETE /api/sales/templates/:locationKey`, `POST /api/sales/templates/upload` (multipart image) → JSON info.
- Sales/auth: `POST /api/sales/auth/login {email,password}`, `POST /api/sales/auth/logout`, `GET /api/sales/auth/me`.
- Chat: `GET /api/sales/chat/history` → `{session_id, messages:[{role,content,files|attachments[]}]}`
  `POST /api/sales/chat/message {conversation_id?,message}`; CRUD: `/conversations`, `/conversation/:id`; `POST /api/sales/chat/stream` body `{conversation_id?,message,file_ids?}` SSE (see below).
- Files: `POST /api/sales/files/upload` multipart `{file}` → `{file_id}`; downloads via signed `url` or `/api/sales/files/:file_id/:filename` (legacy `/api/files/...` remaps).
- Mockup: `GET /api/sales/mockup/locations` → `{locations:[{key,name}]}`; `GET /api/sales/mockup/templates/:location?time_of_day=&finish=` → `{templates:[{photo,time_of_day,finish,frame_count}]}`; `POST /api/sales/mockup/generate` multipart `{location_key,time_of_day,finish,specific_photo?,creative?,ai_prompt?}` → image blob; setup: `POST /api/sales/mockup/setup/save` multipart `{location_key,time_of_day,finish,frames(JSON),photo?}`; `DELETE /api/sales/mockup/setup/delete/:location/:photo`; photo fetch `/api/sales/mockup/photo/:location/:photo`.
- Proposals: `POST /api/sales/proposals/generate` (JSON payload from chat); `GET /api/sales/proposals/history` → `[{client,location,created_at,file_url}]`.
- BO: `GET /api/sales/bo/pending`; `POST /api/sales/bo/:id/approve`; `POST /api/sales/bo/:id/reject {reason}`.
- Modules: `GET /api/modules/accessible` → `{modules:[{name,display_name,description,icon,tools[],is_default,sort_order}], default_module, user_default_module}`.
- Admin: users (`GET /api/admin/users?limit&offset` → `{users:[]}`, `GET /api/admin/users/:id`, `PUT /api/admin/users/:id` JSON, `DELETE /api/admin/users/:id`, `PUT /api/admin/users/:id/profile?profile_name=`, `PUT /api/admin/users/:id/manager?manager_id=`); profiles (`GET /api/admin/profiles` → `{profiles:[]}`, `GET /api/admin/profiles/:name`, `POST/PUT` JSON, `DELETE`); permission-sets (`/api/admin/permission-sets` CRUD, assign/revoke `/api/admin/users/:id/permission-sets/:name` with optional `expires_at`); teams (`/api/admin/teams` CRUD + `/members` add/remove); sharing rules (`/api/admin/sharing-rules` list/create/delete`); permissions (`/api/admin/permissions`, `/api/admin/permissions/grouped`); API keys (`GET /api/admin/api-keys?include_inactive=`, `POST /api/admin/api-keys`, `POST /api/admin/api-keys/:id/rotate`, `POST /api/admin/api-keys/:id/deactivate`, `DELETE /api/admin/api-keys/:id`).

# Chat SSE events (`POST /api/sales/chat/stream`)
- Stream lines prefixed `data:`; `[DONE]` signals end.
- Event shapes: `type:"status"` `{message_id?,content}` (ephemeral); `type:"chunk"` `{message_id?,content}` accumulate; `type:"content"` `{message_id?,content}` replace; `type:"delete"` `{message_id}` resets buffered content; `type:"tool_call"` `{tool:{name}}`; `type:"files"` `{files:[{file_id?,url?,filename,size?,comment?}]}`; `type:"file"` `{file|url,filename,comment}` shorthand. Non-JSON chunks treated as text. If no content and no files, show default "I'm ready…"; if files only, hide empty bubble.

# RBAC rules/behavior
- Profile → roles map: `system_admin → [admin, hos, sales_person]`; `sales_manager → [hos, sales_person]`; `sales_user → [sales_person]`; `coordinator → [coordinator]`; `finance → [finance]`; `viewer → [viewer]`.
- Permissions wildcard match: exact, module-wide (`sales:*:*`), resource-wide (`sales:mockups:*`), action `manage`, or global `*:*:*`; supports dot or colon separators.
- Helpers: `hasPermission`, `hasAny`, `hasAll`, `hasRole`. Admin visibility if `*:*:*` or `core:*:*` or `core:system:admin` (profile `system_admin` also maps to admin role).
- Dev/local mode when Supabase not configured on localhost uses hardcoded users (`admin@mmg.com` etc.) and stores `authToken`/`userData` in `localStorage`.
- 401 responses trigger logout (`auth:logout` event). `/api/base/auth/me` 403 with `USER_PENDING_APPROVAL` shows access-pending instead of loading app.
