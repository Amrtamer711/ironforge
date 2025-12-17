# Frontend API Documentation

This document is designed for full-stack engineers working on the frontend. It covers all API endpoints, request/response schemas, authentication, and integration patterns.

## Table of Contents

- [Authentication](#authentication)
- [API Client Setup](#api-client-setup)
- [Base Endpoints (unified-ui)](#base-endpoints-unified-ui)
- [Chat API](#chat-api)
- [Proposals API](#proposals-api)
- [Mockup API](#mockup-api)
- [Files API](#files-api)
- [Admin API](#admin-api)
- [Modules API](#modules-api)
- [Costs API](#costs-api)
- [Error Handling](#error-handling)
- [Streaming Responses](#streaming-responses)
- [File Uploads](#file-uploads)
- [Frontend Architecture](#frontend-architecture)

---

## Authentication

### Overview

The application uses Supabase Auth with Microsoft SSO for production and email/password for development.

### Authentication Flow

```javascript
// 1. Initialize Supabase client
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// 2. Sign in with Microsoft SSO (Production)
const { data, error } = await supabase.auth.signInWithOAuth({
  provider: 'azure',
  options: {
    redirectTo: window.location.origin
  }
});

// 3. Sign in with email/password (Development)
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password123'
});

// 4. Get session token
const { data: { session } } = await supabase.auth.getSession();
const token = session?.access_token;
```

### Making Authenticated Requests

All API requests must include the Authorization header:

```javascript
const response = await fetch('/api/endpoint', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
```

### Session Management

```javascript
// Check session on page load
const { data: { session } } = await supabase.auth.getSession();
if (session) {
  // User is logged in
  await loadUserProfile();
} else {
  // Show login screen
  showLoginModal();
}

// Listen for auth state changes
supabase.auth.onAuthStateChange((event, session) => {
  if (event === 'SIGNED_IN') {
    loadUserProfile();
  } else if (event === 'SIGNED_OUT') {
    redirectToLogin();
  }
});

// Sign out
await supabase.auth.signOut();
```

---

## API Client Setup

### Base Configuration

```javascript
const API = {
  baseUrl: '', // Same origin (unified-ui proxies to proposal-bot)

  async getToken() {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token;
  },

  async request(endpoint, options = {}) {
    const token = await this.getToken();

    const response = await fetch(endpoint, {
      ...options,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (response.status === 401) {
      // Token expired, sign out
      await supabase.auth.signOut();
      throw new Error('Session expired');
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }
};
```

---

## Base Endpoints (unified-ui)

These endpoints are served directly by unified-ui (not proxied to proposal-bot).

### Get Current User

Fetches the authenticated user's profile, permissions, and companies.

```
GET /api/base/auth/me
```

**Response:**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "John Doe",
    "created_at": "2024-01-15T10:00:00Z"
  },
  "profile": {
    "id": "uuid",
    "name": "sales_user",
    "display_name": "Sales User",
    "is_system": false
  },
  "permissions": [
    "sales:proposals:create",
    "sales:proposals:read",
    "sales:chat:use",
    "sales:mockups:read",
    "sales:mockups:create"
  ],
  "teams": [
    {
      "id": "uuid",
      "name": "Sales North",
      "role": "member"
    }
  ],
  "companies": [
    {
      "id": "uuid",
      "name": "Backlite Dubai",
      "schema": "backlite_dubai"
    }
  ],
  "manager_id": "uuid-or-null"
}
```

### Get Supabase Config

Returns Supabase configuration for client-side initialization.

```
GET /api/base/config.js
```

**Response (JavaScript):**
```javascript
window.SUPABASE_URL = 'https://xxx.supabase.co';
window.SUPABASE_ANON_KEY = 'eyJ...';
```

### Validate Invite Token

```
POST /api/base/auth/validate-invite
```

**Request:**
```json
{
  "token": "invite-token-string"
}
```

**Response:**
```json
{
  "valid": true,
  "email": "invited@example.com",
  "expires_at": "2024-02-01T00:00:00Z"
}
```

### Consume Invite Token

```
POST /api/base/auth/consume-invite
```

**Request:**
```json
{
  "token": "invite-token-string"
}
```

**Response:**
```json
{
  "success": true
}
```

---

## Chat API

### Send Message

Send a message and receive a complete response.

```
POST /api/chat/message
```

**Request:**
```json
{
  "message": "Generate a proposal for Dubai Marina location for 4 weeks",
  "file_ids": ["file-uuid-1", "file-uuid-2"]
}
```

**Response:**
```json
{
  "response": "I'll create a proposal for Dubai Marina...",
  "files": [
    {
      "type": "pdf",
      "name": "Proposal_Dubai_Marina.pdf",
      "url": "/api/files/abc123/Proposal_Dubai_Marina.pdf"
    }
  ],
  "session_id": "session-uuid"
}
```

### Stream Message (SSE)

Send a message and receive a streaming response via Server-Sent Events.

```
POST /api/chat/stream
```

**Request:**
```json
{
  "message": "Explain the pricing structure",
  "file_ids": []
}
```

**Response (SSE Stream):**
```
event: message
data: {"type": "text", "content": "The pricing"}

event: message
data: {"type": "text", "content": " structure includes"}

event: message
data: {"type": "text", "content": " several components..."}

event: file
data: {"type": "file", "name": "rates.pdf", "url": "/api/files/..."}

event: done
data: {"session_id": "session-uuid"}
```

**JavaScript Client:**
```javascript
async function streamChat(message, fileIds = []) {
  const token = await API.getToken();

  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message, file_ids: fileIds })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        handleStreamData(data);
      }
    }
  }
}

function handleStreamData(data) {
  switch (data.type) {
    case 'text':
      appendToMessage(data.content);
      break;
    case 'file':
      addFileAttachment(data.name, data.url);
      break;
  }
}
```

### Get Chat History

```
GET /api/chat/history?session_id={session_id}
```

**Response:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Generate a proposal",
      "timestamp": "2024-01-15T10:00:00Z",
      "files": []
    },
    {
      "role": "assistant",
      "content": "I'll create a proposal for you...",
      "timestamp": "2024-01-15T10:00:05Z",
      "files": [
        {
          "name": "Proposal.pdf",
          "url": "/api/files/..."
        }
      ]
    }
  ]
}
```

### Clear Conversation

```
DELETE /api/chat/history
```

**Response:**
```json
{
  "success": true
}
```

---

## Proposals API

### List Proposals

```
GET /api/proposals?page=1&limit=20&client_name=&date_from=&date_to=
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | number | Page number (default: 1) |
| `limit` | number | Items per page (default: 20, max: 100) |
| `client_name` | string | Filter by client name (partial match) |
| `date_from` | string | Filter from date (ISO 8601) |
| `date_to` | string | Filter to date (ISO 8601) |
| `submitted_by` | string | Filter by user ID (admin only) |

**Response:**
```json
{
  "proposals": [
    {
      "id": "uuid",
      "client_name": "Acme Corp",
      "submitted_by": "user-uuid",
      "submitted_by_name": "John Doe",
      "date_generated": "2024-01-15T10:00:00Z",
      "total_amount": 150000.00,
      "currency": "AED",
      "locations": [
        {
          "location_key": "dubai_marina_01",
          "display_name": "Dubai Marina Tower",
          "start_date": "2024-02-01",
          "duration_weeks": 4,
          "net_rate": 35000.00
        }
      ],
      "file_url": "/api/files/abc123/Proposal_Acme.pdf"
    }
  ],
  "total": 45,
  "page": 1,
  "limit": 20,
  "pages": 3
}
```

### Get Proposal Details

```
GET /api/proposals/{proposal_id}
```

**Response:**
```json
{
  "id": "uuid",
  "client_name": "Acme Corp",
  "submitted_by": "user-uuid",
  "submitted_by_name": "John Doe",
  "date_generated": "2024-01-15T10:00:00Z",
  "total_amount": 150000.00,
  "currency": "AED",
  "vat_amount": 7500.00,
  "grand_total": 157500.00,
  "locations": [
    {
      "location_key": "dubai_marina_01",
      "display_name": "Dubai Marina Tower",
      "start_date": "2024-02-01",
      "end_date": "2024-02-28",
      "duration_weeks": 4,
      "net_rate": 35000.00,
      "municipality_fee": 1750.00
    }
  ],
  "file_url": "/api/files/abc123/Proposal_Acme.pdf",
  "combined_file_url": "/api/files/def456/Proposal_Acme_Combined.pdf"
}
```

### Get Proposal History

```
GET /api/proposals/history?limit=10
```

**Response:**
```json
{
  "history": [
    {
      "id": "uuid",
      "client_name": "Acme Corp",
      "date_generated": "2024-01-15T10:00:00Z",
      "location_count": 3,
      "total_amount": 150000.00
    }
  ]
}
```

---

## Mockup API

### List Locations

Get available locations for mockup generation.

```
GET /api/mockup/locations
```

**Response:**
```json
{
  "locations": [
    {
      "id": "uuid",
      "location_key": "dubai_marina_01",
      "display_name": "Dubai Marina Tower",
      "has_frame": true,
      "variants": {
        "time_of_day": ["day", "night"],
        "finish": ["gold", "silver"]
      },
      "thumbnail_url": "/api/mockup/locations/dubai_marina_01/thumbnail"
    }
  ]
}
```

### Get Location Photos

```
GET /api/mockup/locations/{location_key}/photos
```

**Response:**
```json
{
  "photos": [
    {
      "id": "uuid",
      "time_of_day": "day",
      "finish": "gold",
      "url": "/api/mockup/photos/uuid",
      "has_frame": true
    }
  ]
}
```

### Generate Mockup

```
POST /api/mockup/generate
```

**Request:**
```json
{
  "location_key": "dubai_marina_01",
  "creative_file_id": "file-uuid",
  "time_of_day": "day",
  "finish": "gold",
  "config_overrides": {
    "brightness": 1.1,
    "contrast": 1.0,
    "saturation": 0.95
  }
}
```

**Response:**
```json
{
  "mockup_url": "/api/files/mockup-uuid/Dubai_Marina_Mockup.jpg",
  "mockup_id": "mockup-uuid",
  "location": {
    "key": "dubai_marina_01",
    "display_name": "Dubai Marina Tower"
  }
}
```

### Save Frame (Admin Only)

Save billboard frame coordinates for a location photo.

```
POST /api/mockup/save-frame
```

**Request:**
```json
{
  "location_key": "dubai_marina_01",
  "photo_id": "photo-uuid",
  "frame_points": [
    {"x": 100, "y": 150},
    {"x": 400, "y": 150},
    {"x": 400, "y": 350},
    {"x": 100, "y": 350}
  ],
  "config": {
    "brightness": 1.0,
    "contrast": 1.0,
    "saturation": 1.0,
    "blur": 0,
    "depth_enabled": false
  }
}
```

**Response:**
```json
{
  "success": true,
  "frame_id": "frame-uuid"
}
```

### Upload Location Photo (Admin Only)

```
POST /api/mockup/upload-photo
Content-Type: multipart/form-data
```

**Form Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `photo` | File | Billboard photo (JPEG/PNG) |
| `location_key` | string | Location identifier |
| `time_of_day` | string | "day" or "night" |
| `finish` | string | "gold" or "silver" |

**Response:**
```json
{
  "photo_id": "uuid",
  "url": "/api/mockup/photos/uuid"
}
```

---

## Files API

### Upload Single File

```
POST /api/files/upload
Content-Type: multipart/form-data
```

**Form Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `file` | File | File to upload (max 200MB) |

**Allowed Types:**
- Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Documents: `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`

**Response:**
```json
{
  "file_id": "uuid",
  "filename": "creative.jpg",
  "url": "/api/files/uuid/creative.jpg",
  "size": 1048576,
  "mime_type": "image/jpeg"
}
```

### Upload Multiple Files

```
POST /api/files/upload/multi
Content-Type: multipart/form-data
```

**Form Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `files` | File[] | Files to upload (max 10 files) |

**Response:**
```json
{
  "files": [
    {
      "file_id": "uuid-1",
      "filename": "image1.jpg",
      "url": "/api/files/uuid-1/image1.jpg"
    },
    {
      "file_id": "uuid-2",
      "filename": "document.pdf",
      "url": "/api/files/uuid-2/document.pdf"
    }
  ]
}
```

### Download File

```
GET /api/files/{file_id}/{filename}
```

**Response:** File binary with appropriate Content-Type header.

### JavaScript Upload Example

```javascript
async function uploadFile(file) {
  const token = await API.getToken();
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/files/upload', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
      // Don't set Content-Type - browser will set it with boundary
    },
    body: formData
  });

  if (!response.ok) {
    throw new Error('Upload failed');
  }

  return response.json();
}

// Usage
const fileInput = document.getElementById('file-input');
fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  try {
    const result = await uploadFile(file);
    console.log('Uploaded:', result.file_id);
  } catch (error) {
    console.error('Upload error:', error);
  }
});
```

---

## Admin API

**Note:** All admin endpoints require `core:users:manage` or `core:system:admin` permission.

### List Users

```
GET /api/admin/users?page=1&limit=20&search=
```

**Response:**
```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "name": "John Doe",
      "profile": {
        "id": "uuid",
        "name": "sales_user",
        "display_name": "Sales User"
      },
      "teams": ["Sales North"],
      "companies": ["Backlite Dubai"],
      "created_at": "2024-01-15T10:00:00Z",
      "last_login": "2024-01-20T15:30:00Z"
    }
  ],
  "total": 50,
  "page": 1,
  "limit": 20
}
```

### Create User

```
POST /api/admin/users
```

**Request:**
```json
{
  "email": "newuser@example.com",
  "name": "Jane Smith",
  "profile_id": "profile-uuid",
  "team_ids": ["team-uuid"],
  "company_ids": ["company-uuid"]
}
```

**Response:**
```json
{
  "user": {
    "id": "new-user-uuid",
    "email": "newuser@example.com",
    "name": "Jane Smith"
  },
  "invite_sent": true
}
```

### Update User

```
PATCH /api/admin/users/{user_id}
```

**Request:**
```json
{
  "name": "Jane Smith Updated",
  "profile_id": "new-profile-uuid",
  "team_ids": ["team-uuid-1", "team-uuid-2"],
  "company_ids": ["company-uuid"]
}
```

### Delete User

```
DELETE /api/admin/users/{user_id}
```

### List Profiles

```
GET /api/admin/profiles
```

**Response:**
```json
{
  "profiles": [
    {
      "id": "uuid",
      "name": "sales_user",
      "display_name": "Sales User",
      "description": "Standard sales team member",
      "is_system": false,
      "permissions": [
        "sales:proposals:create",
        "sales:proposals:read",
        "sales:chat:use"
      ]
    }
  ]
}
```

### Create Profile

```
POST /api/admin/profiles
```

**Request:**
```json
{
  "name": "sales_coordinator",
  "display_name": "Sales Coordinator",
  "description": "Coordinates sales and booking orders",
  "permissions": [
    "sales:proposals:*",
    "sales:bo:*",
    "sales:chat:use"
  ]
}
```

### List Teams

```
GET /api/admin/teams
```

**Response:**
```json
{
  "teams": [
    {
      "id": "uuid",
      "name": "Sales North",
      "parent_team_id": null,
      "members": [
        {
          "user_id": "uuid",
          "user_name": "John Doe",
          "role": "leader"
        }
      ]
    }
  ]
}
```

### Send Invite

```
POST /api/admin/invites
```

**Request:**
```json
{
  "email": "newhire@example.com",
  "profile_id": "profile-uuid",
  "team_ids": ["team-uuid"],
  "company_ids": ["company-uuid"],
  "expires_in_days": 7
}
```

**Response:**
```json
{
  "invite_token": "token-string",
  "invite_url": "https://app.example.com/invite?token=...",
  "expires_at": "2024-01-22T10:00:00Z"
}
```

---

## Modules API

### Get Accessible Modules

```
GET /api/modules
```

**Response:**
```json
{
  "modules": [
    {
      "id": "uuid",
      "name": "sales",
      "display_name": "Sales",
      "icon": "chart-bar",
      "is_default": true,
      "tools": [
        {
          "name": "chat",
          "display_name": "AI Chat",
          "icon": "message-circle"
        },
        {
          "name": "mockup",
          "display_name": "Mockup Generator",
          "icon": "image"
        },
        {
          "name": "proposals",
          "display_name": "Proposals",
          "icon": "file-text"
        }
      ]
    },
    {
      "id": "uuid",
      "name": "admin",
      "display_name": "Admin",
      "icon": "settings",
      "is_default": false,
      "tools": [
        {
          "name": "users",
          "display_name": "Users",
          "icon": "users"
        }
      ]
    }
  ]
}
```

### Get Module Details

```
GET /api/modules/{module_name}
```

---

## Costs API

### Get Cost Summary

```
GET /costs?date_from=&date_to=&workflow=
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `date_from` | string | Start date (ISO 8601) |
| `date_to` | string | End date (ISO 8601) |
| `workflow` | string | Filter by workflow (chat, proposal, mockup) |
| `user_id` | string | Filter by user (admin only) |

**Response:**
```json
{
  "total_cost": 125.50,
  "currency": "USD",
  "breakdown": {
    "by_provider": {
      "openai": 100.00,
      "google": 25.50
    },
    "by_workflow": {
      "chat": 80.00,
      "proposal": 30.00,
      "mockup": 15.50
    },
    "by_date": [
      {"date": "2024-01-15", "cost": 45.00},
      {"date": "2024-01-16", "cost": 80.50}
    ]
  },
  "calls": [
    {
      "id": "uuid",
      "timestamp": "2024-01-15T10:00:00Z",
      "provider": "openai",
      "model": "gpt-4-turbo",
      "workflow": "chat",
      "tokens_in": 1500,
      "tokens_out": 500,
      "cost": 0.045,
      "user_id": "user-uuid"
    }
  ]
}
```

---

## Error Handling

### Error Response Format

All API errors return this format:

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid/expired token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found |
| 413 | Payload Too Large - File too big |
| 422 | Validation Error |
| 429 | Too Many Requests - Rate limited |
| 500 | Internal Server Error |

### Error Handling Example

```javascript
async function apiRequest(endpoint, options) {
  try {
    const response = await fetch(endpoint, options);

    if (response.status === 401) {
      // Session expired
      await supabase.auth.signOut();
      window.location.href = '/login';
      return;
    }

    if (response.status === 403) {
      showToast('You do not have permission to perform this action', 'error');
      return;
    }

    if (response.status === 429) {
      showToast('Too many requests. Please wait a moment.', 'warning');
      return;
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  } catch (error) {
    console.error('API Error:', error);
    showToast(error.message, 'error');
    throw error;
  }
}
```

---

## Streaming Responses

### Server-Sent Events (SSE)

The chat streaming endpoint uses SSE for real-time responses.

```javascript
class ChatStream {
  constructor() {
    this.abortController = null;
  }

  async stream(message, fileIds, onChunk, onFile, onDone) {
    this.abortController = new AbortController();
    const token = await API.getToken();

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message, file_ids: fileIds }),
      signal: this.abortController.signal
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            const eventType = line.split('\n')[0].slice(7);
            const dataLine = line.split('\n')[1];

            if (dataLine && dataLine.startsWith('data: ')) {
              const data = JSON.parse(dataLine.slice(6));

              switch (eventType) {
                case 'message':
                  onChunk(data.content);
                  break;
                case 'file':
                  onFile(data);
                  break;
                case 'done':
                  onDone(data);
                  break;
              }
            }
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Stream aborted');
      } else {
        throw error;
      }
    }
  }

  abort() {
    if (this.abortController) {
      this.abortController.abort();
    }
  }
}

// Usage
const chatStream = new ChatStream();

await chatStream.stream(
  'Generate a proposal',
  [],
  (text) => {
    // Append text to message
    messageElement.textContent += text;
  },
  (file) => {
    // Handle file attachment
    addFileAttachment(file.name, file.url);
  },
  (data) => {
    // Stream complete
    console.log('Done, session:', data.session_id);
  }
);
```

---

## File Uploads

### Drag and Drop Upload

```javascript
class FileUploader {
  constructor(dropZone, options = {}) {
    this.dropZone = dropZone;
    this.maxSize = options.maxSize || 200 * 1024 * 1024; // 200MB
    this.allowedTypes = options.allowedTypes || [
      'image/jpeg', 'image/png', 'image/gif', 'image/webp',
      'application/pdf',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];

    this.setupListeners();
  }

  setupListeners() {
    this.dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.dropZone.classList.add('drag-over');
    });

    this.dropZone.addEventListener('dragleave', () => {
      this.dropZone.classList.remove('drag-over');
    });

    this.dropZone.addEventListener('drop', async (e) => {
      e.preventDefault();
      this.dropZone.classList.remove('drag-over');

      const files = Array.from(e.dataTransfer.files);
      await this.uploadFiles(files);
    });
  }

  validateFile(file) {
    if (file.size > this.maxSize) {
      throw new Error(`File ${file.name} exceeds maximum size of 200MB`);
    }

    if (!this.allowedTypes.includes(file.type)) {
      throw new Error(`File type ${file.type} is not allowed`);
    }

    return true;
  }

  async uploadFiles(files) {
    const results = [];

    for (const file of files) {
      try {
        this.validateFile(file);
        const result = await this.uploadFile(file);
        results.push(result);
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        showToast(error.message, 'error');
      }
    }

    return results;
  }

  async uploadFile(file) {
    const token = await API.getToken();
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/files/upload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
  }
}
```

### Progress Tracking

```javascript
async function uploadWithProgress(file, onProgress) {
  const token = await API.getToken();
  const formData = new FormData();
  formData.append('file', file);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error('Upload failed'));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error')));

    xhr.open('POST', '/api/files/upload');
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.send(formData);
  });
}
```

---

## Frontend Architecture

### Module Structure

```javascript
// modules.js - Module registry
const Modules = {
  registered: {},

  register(name, module) {
    this.registered[name] = module;
  },

  async init() {
    const { modules } = await API.modules.list();

    for (const mod of modules) {
      if (this.registered[mod.name]) {
        await this.registered[mod.name].init();
      }
    }
  },

  show(name) {
    Object.values(this.registered).forEach(m => m.hide?.());
    this.registered[name]?.show?.();
  }
};

// Register modules
Modules.register('chat', Chat);
Modules.register('mockup', Mockup);
Modules.register('admin', Admin);
```

### State Management

```javascript
// Simple state management
const State = {
  user: null,
  permissions: [],
  currentModule: 'chat',

  setUser(user, permissions) {
    this.user = user;
    this.permissions = permissions;
    this.emit('user-changed', user);
  },

  hasPermission(permission) {
    return this.permissions.some(p => {
      if (p === '*:*:*') return true;
      const [pMod, pRes, pAct] = p.split(':');
      const [rMod, rRes, rAct] = permission.split(':');
      return (
        (pMod === '*' || pMod === rMod) &&
        (pRes === '*' || pRes === rRes) &&
        (pAct === '*' || pAct === rAct)
      );
    });
  },

  listeners: {},

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
  },

  emit(event, data) {
    (this.listeners[event] || []).forEach(cb => cb(data));
  }
};
```

### Component Pattern

```javascript
// Base component pattern
class Component {
  constructor(container) {
    this.container = typeof container === 'string'
      ? document.querySelector(container)
      : container;
  }

  render() {
    throw new Error('render() must be implemented');
  }

  show() {
    this.container.style.display = 'block';
  }

  hide() {
    this.container.style.display = 'none';
  }

  destroy() {
    this.container.innerHTML = '';
  }
}

// Example: Chat component
class ChatComponent extends Component {
  constructor() {
    super('#chat-container');
    this.messages = [];
  }

  async init() {
    this.render();
    await this.loadHistory();
    this.setupListeners();
  }

  render() {
    this.container.innerHTML = `
      <div class="chat-messages" id="chat-messages"></div>
      <div class="chat-input">
        <textarea id="chat-input" placeholder="Type a message..."></textarea>
        <button id="chat-send">Send</button>
      </div>
    `;
  }

  async loadHistory() {
    const { messages } = await API.chat.history();
    this.messages = messages;
    this.renderMessages();
  }

  renderMessages() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = this.messages.map(m => `
      <div class="message message-${m.role}">
        ${m.content}
      </div>
    `).join('');
  }

  setupListeners() {
    document.getElementById('chat-send').addEventListener('click', () => {
      this.sendMessage();
    });
  }

  async sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    this.addMessage({ role: 'user', content: message });

    // Stream response
    const chatStream = new ChatStream();
    let response = '';

    await chatStream.stream(
      message,
      [],
      (text) => {
        response += text;
        this.updateLastMessage(response);
      },
      (file) => {
        this.addFileAttachment(file);
      },
      () => {
        this.addMessage({ role: 'assistant', content: response });
      }
    );
  }
}
```

---

## Quick Reference

### Common Operations

```javascript
// Check if user can create proposals
if (State.hasPermission('sales:proposals:create')) {
  showCreateButton();
}

// Upload file and attach to chat
const file = await uploadFile(selectedFile);
await chatStream.stream(message, [file.file_id], ...);

// Generate mockup
const mockup = await API.mockup.generate({
  location_key: 'dubai_marina_01',
  creative_file_id: file.file_id,
  time_of_day: 'day',
  finish: 'gold'
});

// List proposals with filters
const { proposals } = await API.proposals.list({
  page: 1,
  limit: 20,
  client_name: 'Acme'
});
```

---

## Support

For API issues, check:
1. Browser console for errors
2. Network tab for request/response details
3. Server logs at `/health` endpoint
4. Contact development team
