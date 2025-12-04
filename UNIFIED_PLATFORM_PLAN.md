# Unified AI Platform - Architecture & Implementation Plan

## Vision

Build a next-generation unified AI platform that consolidates all BackLite Media sales operations into a single, modern interface. This platform will serve as the central hub for AI-powered business operations, replacing Slack dependency while maintaining backward compatibility.

The platform must embody the aesthetic of a cutting-edge AI startup - sleek, powerful, and unmistakably futuristic.

### Key Architecture Principles

1. **FastAPI-Only Communication** - The unified UI communicates with the backend EXCLUSIVELY through FastAPI endpoints. No direct database access, no direct LLM calls, no direct storage access from the frontend.

2. **Expand mockup-studio → unified-ui** - Not a new project. The existing mockup-studio codebase evolves into the unified platform, keeping all existing mockup functionality while adding new features.

3. **Supabase Auth** - Production uses Supabase for authentication. Local dev can use simple auth via FastAPI.

4. **Module-Based Architecture** - The platform is organized by department modules. Users can have multiple roles within a module.

---

## Unified UI: Sales Department Module

The Sales Department is the first module implementation.

### Roles (a user can have multiple)

| Role | Permissions |
|------|-------------|
| `sales_person` | Create proposals, generate mockups, use chat AI |
| `hos` | All sales_person + BO approval, team oversight |
| `admin` | All permissions + user management, system config |

### UI Layout

Single sidebar with tool selection. Main area shows the selected tool. Sidebar shows tool-specific settings.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MMG Logo                                        User Menu ▼  [Logout]  │
├─────────────┬───────────────────────────────────────────────────────────┤
│             │                                                           │
│  SIDEBAR    │                    MAIN CONTENT AREA                      │
│             │                                                           │
│  ┌────────┐ │    (Changes based on selected tool in sidebar)            │
│  │ 💬 Chat │ │                                                           │
│  └────────┘ │    CHAT: ChatGPT-style interface                          │
│  ▼ Settings │           - Message input                                 │
│    - History│           - Streaming responses                           │
│    - New    │           - File attachments                              │
│             │           - Generated outputs inline                      │
│  ┌────────┐ │                                                           │
│  │ 🖼️ Mockup│ │    MOCKUP: Full mockup generator canvas                  │
│  └────────┘ │           - Canvas with frame drawing                     │
│  ▼ Settings │           - All existing mockup-studio features           │
│    - Setup  │                                                           │
│    - Generate│                                                          │
│             │                                                           │
│  ┌────────┐ │    PROPOSALS: Proposal generation interface               │
│  │ 📄 Props │ │                                                           │
│  └────────┘ │    BOs: Booking order management                          │
│             │                                                           │
│  ┌────────┐ │                                                           │
│  │ 📋 BOs  │ │                                                           │
│  └────────┘ │                                                           │
│             │                                                           │
│  ─────────  │                                                           │
│  ⚙️ Settings │                                                           │
│             │                                                           │
└─────────────┴───────────────────────────────────────────────────────────┘
```

### Tool Behavior

- **Clicking a tool** → Opens that tool in main content area + expands tool-specific settings in sidebar
- **Chat** → Settings: conversation history, new chat button
- **Mockup Generator** → Settings: Setup mode / Generate mode toggle (existing functionality)
- **Proposals** → Settings: recent proposals, templates
- **BOs** → Settings: pending approvals (based on role), filters

---

## Current System Overview

### What We Have Today

**BackLite Media Sales Operations Bot** - A production AI system handling:

#### 1. Proposal Generation
- Natural language requests via Slack: "Create a proposal for Nike at The Landmark for 2 weeks"
- Generates professional PowerPoint decks from 25+ location templates
- Features:
  - Multiple durations/rates per location
  - Combined package proposals (multiple locations, single rate)
  - Multi-currency support (AED base, USD/EUR/GBP/SAR with exchange rates)
  - Automatic upload fee calculation for digital billboards
  - VAT calculation (5%)
  - PDF conversion via LibreOffice
  - Direct upload to Slack

#### 2. Mockup Generation
- User uploads creative images + specifies location
- Composites creatives onto real billboard photos using:
  - Perspective warp (cv2.warpPerspective with 4-point transformation)
  - 4x MSAA anti-aliasing via EdgeCompositor
  - Gamma-correct Gaussian blur
  - Color adjustments (brightness, contrast, saturation, temperature)
  - Depth effects (night glow, day haze)
  - Vignette, sharpening, shadow intensity
- Frame matching logic:
  - 1 image → duplicated across all frames
  - N images → requires location with exactly N frames
- 30-minute creative cache for multi-location batches

#### 3. AI Creative Generation
- Generate billboard creatives from text prompts
- Uses Google Gemini-3-pro-image-preview
- Prompts optimized for flat, print-ready artwork (not mockups)
- Supports portrait (2:3) and landscape (3:2) aspect ratios

#### 4. Booking Order (BO) Approval Workflow
- Upload BO PDF/Excel → LLM extracts structured data
- Multi-stage approval state machine:
  ```
  Sales Person → Coordinator (can edit) → Head of Sales → Finance
  ```
- In-thread editing: "change municipality fee to 8000" → LLM interprets → auto-recalculates
- Extracted fields: BO number, client, brand, locations, fees, tenure, VAT, gross amount
- Generates standardized Excel output
- Document classification (Backlite vs Viola)

#### 5. Cost Analytics Dashboard
- Tracks all LLM API costs (input, cached, output, reasoning tokens)
- Per-provider pricing calculation
- Usage analytics by user, workflow, model

#### 6. Mockup Studio (WIP)
- Web-based billboard frame editor
- Upload photos, draw quadrilateral frames
- Configure per-frame effects (brightness, blur, etc.)
- Green screen auto-detection
- Test preview with live effect adjustment

### Current Tech Stack

| Layer | Technology | Status |
|-------|------------|--------|
| **Backend** | FastAPI + Python 3.11 + Uvicorn | ✅ Production |
| **Database** | SQLite3 | ⚠️ Works, limited |
| **Storage** | Render disk (5GB at /data/) | ⚠️ Not scalable |
| **Auth** | Slack-based only | ⚠️ Tied to Slack |
| **Text LLM** | OpenAI GPT-5.1 OR Google Gemini-2.5-flash | ✅ Abstracted |
| **Image LLM** | Google Gemini-3-pro-image-preview | ✅ Working |
| **Doc Gen** | python-pptx + LibreOffice | ✅ Production |
| **Image Processing** | OpenCV + Pillow + NumPy | ✅ Production |
| **Slack SDK** | slack-sdk 3.26.1 | ✅ Production |
| **Cost Dashboard** | Express.js + Vanilla JS | ✅ Working |
| **Mockup Studio** | Express.js + Vanilla JS | 🚧 In Progress |
| **Hosting** | Render.com + Docker | ✅ Production |

### Current Database Schema

```sql
-- Proposal tracking
proposals_log (client_name, date_generated, package_type, locations_json, total_amount, currency, submitted_by)

-- Billboard frame coordinates for compositing
mockup_frames (location_key, time_of_day, finish, photo_filename, frames_data_json, config_json)

-- Mockup generation analytics
mockup_usage (timestamp, user_id, location_key, time_of_day, finish, creative_type, ai_prompt, success)

-- Booking order data + approval state
booking_orders (bo_ref, company, bo_number, client, locations_json, net_pre_vat, vat_value, gross_amount, approval_state, warnings_json)

-- Active BO review sessions
bo_approval_workflows (workflow_id, workflow_data_json, created_at, updated_at)

-- Comprehensive AI cost tracking
ai_costs (timestamp, call_type, model, user_id, input_tokens, cached_tokens, output_tokens, reasoning_tokens, input_cost, output_cost, reasoning_cost, total_cost, metadata_json, workflow)
```

### Current Directory Structure

```
Sales Proposals/
├── main.py                    # Entry point (uvicorn)
├── config.py                  # Central config (21KB) - locations, currency, permissions
├── requirements.txt
├── Dockerfile                 # Python 3.11 + LibreOffice
├── render.yaml                # Render deployment config
│
├── api/
│   └── server.py              # FastAPI routes, Slack webhook
│
├── core/
│   ├── llm.py                 # Main conversation loop (1200+ lines)
│   ├── proposals.py           # Proposal generation workflow
│   └── tools.py               # LLM function definitions
│
├── integrations/
│   ├── llm/                   # ⭐ Well-abstracted LLM layer
│   │   ├── client.py          # LLMClient - provider agnostic
│   │   ├── base.py            # Abstract classes
│   │   ├── cost_tracker.py    # Cost logging
│   │   ├── providers/
│   │   │   ├── openai.py      # GPT-5.1, GPT-image-1
│   │   │   └── google.py      # Gemini-2.5-flash, Gemini-3-pro-image
│   │   ├── prompts/
│   │   │   ├── chat.py        # System prompt
│   │   │   ├── mockup.py      # AI creative prompt
│   │   │   ├── bo_parsing.py  # BO extraction prompt
│   │   │   └── bo_editing.py  # BO edit interpretation
│   │   └── schemas/           # JSON schemas for structured output
│   │
│   └── slack/
│       ├── formatting.py      # SlackResponses helper
│       ├── bo_messaging.py    # BO workflow messages
│       └── file_utils.py      # File download/validation
│
├── generators/
│   ├── pptx.py                # PowerPoint generation
│   ├── pdf.py                 # PDF conversion (LibreOffice)
│   ├── mockup.py              # Mockup orchestration
│   └── effects/               # ⭐ Modular image processing
│       ├── compositor.py      # BillboardCompositor, perspective warp
│       ├── edge.py            # EdgeCompositor (4x MSAA)
│       ├── depth.py           # DepthEffect, Vignette, Shadow
│       ├── color.py           # ColorAdjustment, Blur, Sharpening
│       └── config.py          # EffectConfig dataclass
│
├── routers/
│   ├── tool_router.py         # LLM function call dispatch
│   ├── mockup_handler.py      # Mockup generation handler
│   └── file_classifier.py     # File type detection
│
├── workflows/
│   ├── bo_parser.py           # BookingOrderParser
│   └── bo_approval.py         # BO approval state machine
│
├── db/
│   ├── database.py            # SQLite schema, ORM
│   └── cache.py               # In-memory caches (user history, mockup history)
│
├── utils/
│   ├── memory.py              # Centralized GC
│   └── task_queue.py          # MockupTaskQueue (max 3 concurrent)
│
├── dashboard/                 # Cost analytics (Express.js)
├── unified-ui/                # 🔄 Unified Platform UI (expanded from mockup-studio)
│   ├── server.js              # Express server (local dev)
│   ├── package.json
│   └── public/
│       ├── index.html         # Landing page + Auth + App shell
│       ├── css/styles.css     # Cosmic design system
│       └── js/
│           ├── app.js         # Main application (mockup functionality)
│           ├── auth.js        # Supabase auth / local auth
│           ├── chat.js        # Chat interface module
│           ├── sidebar.js     # Sidebar navigation + tool settings
│           └── api.js         # FastAPI communication layer
│
├── render_main_data/          # Dev data
│   ├── templates/             # 25+ location PPTX templates
│   ├── mockups/               # Billboard photos by location/time/finish
│   └── currency_config.json
│
└── bo_templates/              # Booking order Excel templates
```

---

## Why Migrate to Supabase First?

### Current Limitations

| Problem | Impact |
|---------|--------|
| **SQLite** | No concurrent writes, no real-time, no backups, single-file DB |
| **File storage on Render** | 5GB limit, no CDN, no signed URLs, tied to single instance |
| **Auth tied to Slack** | Cannot build web UI without new auth system |
| **No real-time** | WebSockets would need to be built from scratch |
| **Multiple Node services** | Dashboard + Mockup Studio duplicated, separate deployments |

### What Supabase Provides

| Feature | Benefit |
|---------|---------|
| **PostgreSQL** | Real database - concurrent access, full SQL, backups, migrations |
| **Auth** | Email/password, magic links, OAuth (Google), SSO-ready |
| **Storage** | S3-compatible, CDN-backed, signed URLs, 100GB+ |
| **Real-time** | WebSocket subscriptions out of the box |
| **Row Level Security** | Secure multi-tenant from day 1 |
| **Edge Functions** | Serverless if needed |
| **Free tier** | 500MB DB, 1GB storage, 50K MAU |

### Migration Complexity: **Medium** (1-2 weeks)

Your schema is clean and maps directly to PostgreSQL. The hardest part is file storage migration.

---

## Phase 0: Backend Foundation (Supabase Migration)

### 0.1 Supabase Project Setup

```bash
# Create project at supabase.com
# Get credentials:
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...  # For backend
```

### 0.2 Database Schema Migration

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- PROPOSALS
-- ============================================
CREATE TABLE proposals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_name TEXT NOT NULL,
  package_type TEXT NOT NULL,  -- 'separate' | 'combined'
  locations JSONB NOT NULL,
  total_amount DECIMAL(12,2),
  currency TEXT DEFAULT 'AED',
  submitted_by TEXT,  -- Slack user ID or Web user ID
  channel_source TEXT DEFAULT 'slack',  -- 'slack' | 'web' | 'api'
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- File references (Supabase Storage)
  pptx_path TEXT,
  pdf_path TEXT
);

-- ============================================
-- MOCKUP FRAMES (Billboard templates)
-- ============================================
CREATE TABLE mockup_frames (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  location_key TEXT NOT NULL,
  time_of_day TEXT NOT NULL,  -- 'day' | 'night'
  finish TEXT NOT NULL,        -- 'gold' | 'silver'
  photo_filename TEXT NOT NULL,
  photo_path TEXT NOT NULL,    -- Supabase Storage path
  frames_data JSONB NOT NULL,  -- Array of frame coordinates
  config JSONB,                -- Default effect settings
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(location_key, time_of_day, finish, photo_filename)
);

CREATE INDEX idx_mockup_frames_location ON mockup_frames(location_key);

-- ============================================
-- MOCKUP USAGE (Analytics)
-- ============================================
CREATE TABLE mockup_usage (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id TEXT NOT NULL,
  location_key TEXT NOT NULL,
  time_of_day TEXT,
  finish TEXT,
  creative_type TEXT,  -- 'uploaded' | 'ai_generated'
  ai_prompt TEXT,
  success BOOLEAN DEFAULT true,
  error_message TEXT,
  channel_source TEXT DEFAULT 'slack',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_mockup_usage_user ON mockup_usage(user_id);
CREATE INDEX idx_mockup_usage_location ON mockup_usage(location_key);

-- ============================================
-- BOOKING ORDERS
-- ============================================
CREATE TABLE booking_orders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  bo_ref TEXT UNIQUE NOT NULL,
  company TEXT NOT NULL,  -- 'backlite' | 'viola'
  bo_number TEXT,
  client TEXT,
  brand_campaign TEXT,
  category TEXT,
  locations JSONB,
  tenure_start DATE,
  tenure_end DATE,
  municipality_fee DECIMAL(12,2),
  production_fee DECIMAL(12,2),
  net_pre_vat DECIMAL(12,2),
  vat_value DECIMAL(12,2),
  gross_amount DECIMAL(12,2),
  payment_terms TEXT,
  approval_state TEXT DEFAULT 'pending',
  warnings JSONB,
  parsed_by TEXT,
  channel_source TEXT DEFAULT 'slack',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bo_client ON booking_orders(client);
CREATE INDEX idx_bo_state ON booking_orders(approval_state);

-- ============================================
-- BO APPROVAL WORKFLOWS
-- ============================================
CREATE TABLE bo_workflows (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  bo_id UUID REFERENCES booking_orders(id),
  current_stage TEXT NOT NULL,  -- 'coordinator' | 'hos' | 'finance'
  workflow_data JSONB NOT NULL,
  slack_thread_ts TEXT,
  web_session_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- AI COSTS (Comprehensive tracking)
-- ============================================
CREATE TABLE ai_costs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  call_type TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  user_id TEXT,
  channel_source TEXT DEFAULT 'slack',

  -- Token counts
  input_tokens INTEGER DEFAULT 0,
  cached_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  reasoning_tokens INTEGER DEFAULT 0,
  image_output_tokens INTEGER DEFAULT 0,

  -- Costs (USD)
  input_cost DECIMAL(10,6) DEFAULT 0,
  output_cost DECIMAL(10,6) DEFAULT 0,
  reasoning_cost DECIMAL(10,6) DEFAULT 0,
  total_cost DECIMAL(10,6) DEFAULT 0,

  -- Context
  workflow TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_costs_user ON ai_costs(user_id);
CREATE INDEX idx_ai_costs_date ON ai_costs(created_at);
CREATE INDEX idx_ai_costs_workflow ON ai_costs(workflow);

-- ============================================
-- LOCATIONS (Template metadata)
-- ============================================
CREATE TABLE locations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  location_key TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  series TEXT,
  width_m DECIMAL(5,2),
  height_m DECIMAL(5,2),
  upload_fee DECIMAL(10,2) DEFAULT 0,
  is_digital BOOLEAN DEFAULT false,
  template_path TEXT,  -- Supabase Storage path to PPTX
  metadata JSONB,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- USERS (For web auth + linking to Slack)
-- ============================================
CREATE TABLE users (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  email TEXT UNIQUE,
  full_name TEXT,
  slack_user_id TEXT UNIQUE,  -- Link to Slack identity
  role TEXT DEFAULT 'user',   -- 'admin' | 'coordinator' | 'hos' | 'user'
  company TEXT,               -- 'backlite' | 'viola'
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_slack ON users(slack_user_id);

-- ============================================
-- CONVERSATIONS (Chat history for web UI)
-- ============================================
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  title TEXT,
  messages JSONB DEFAULT '[]',
  channel_source TEXT DEFAULT 'web',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversations_user ON conversations(user_id);
```

### 0.3 Storage Bucket Structure

```
supabase-storage/
├── templates/                    # PPTX templates
│   ├── the_landmark/
│   │   ├── template.pptx
│   │   └── metadata.json
│   └── ...
│
├── mockup-photos/               # Billboard photos
│   ├── the_landmark/
│   │   ├── day/
│   │   │   ├── gold/
│   │   │   │   └── photo1.jpg
│   │   │   └── silver/
│   │   └── night/
│   └── ...
│
├── generated/                   # Generated outputs
│   ├── proposals/
│   │   └── {uuid}.pdf
│   ├── mockups/
│   │   └── {uuid}.jpg
│   └── booking-orders/
│       └── {uuid}.xlsx
│
└── uploads/                     # User uploads
    └── {user_id}/
        └── {uuid}.{ext}
```

### 0.4 Python Migration Layer

```python
# integrations/db/supabase_client.py

from supabase import create_client, Client
from typing import Optional
import os

class SupabaseClient:
    """Supabase client wrapper with backward-compatible interface."""

    def __init__(self):
        self.client: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )

    # ==========================================
    # PROPOSALS
    # ==========================================

    async def log_proposal(
        self,
        client_name: str,
        package_type: str,
        locations: list,
        total_amount: float,
        currency: str,
        submitted_by: str,
        channel_source: str = "slack",
        pptx_path: Optional[str] = None,
        pdf_path: Optional[str] = None
    ) -> dict:
        """Log a generated proposal."""
        result = self.client.table("proposals").insert({
            "client_name": client_name,
            "package_type": package_type,
            "locations": locations,
            "total_amount": total_amount,
            "currency": currency,
            "submitted_by": submitted_by,
            "channel_source": channel_source,
            "pptx_path": pptx_path,
            "pdf_path": pdf_path
        }).execute()
        return result.data[0]

    # ==========================================
    # MOCKUP FRAMES
    # ==========================================

    async def get_mockup_frames(
        self,
        location_key: str,
        time_of_day: Optional[str] = None,
        finish: Optional[str] = None
    ) -> list:
        """Get mockup frame templates for a location."""
        query = self.client.table("mockup_frames").select("*").eq("location_key", location_key)

        if time_of_day:
            query = query.eq("time_of_day", time_of_day)
        if finish:
            query = query.eq("finish", finish)

        result = query.execute()
        return result.data

    async def save_mockup_frame(
        self,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_filename: str,
        photo_path: str,
        frames_data: list,
        config: Optional[dict] = None
    ) -> dict:
        """Save or update a mockup frame template."""
        result = self.client.table("mockup_frames").upsert({
            "location_key": location_key,
            "time_of_day": time_of_day,
            "finish": finish,
            "photo_filename": photo_filename,
            "photo_path": photo_path,
            "frames_data": frames_data,
            "config": config
        }, on_conflict="location_key,time_of_day,finish,photo_filename").execute()
        return result.data[0]

    # ==========================================
    # AI COSTS
    # ==========================================

    async def log_ai_cost(
        self,
        call_type: str,
        provider: str,
        model: str,
        user_id: str,
        input_tokens: int,
        output_tokens: int,
        total_cost: float,
        channel_source: str = "slack",
        **kwargs
    ) -> dict:
        """Log an AI API call cost."""
        result = self.client.table("ai_costs").insert({
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "user_id": user_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
            "channel_source": channel_source,
            "cached_tokens": kwargs.get("cached_tokens", 0),
            "reasoning_tokens": kwargs.get("reasoning_tokens", 0),
            "image_output_tokens": kwargs.get("image_output_tokens", 0),
            "input_cost": kwargs.get("input_cost", 0),
            "output_cost": kwargs.get("output_cost", 0),
            "reasoning_cost": kwargs.get("reasoning_cost", 0),
            "workflow": kwargs.get("workflow"),
            "metadata": kwargs.get("metadata")
        }).execute()
        return result.data[0]

    # ==========================================
    # STORAGE
    # ==========================================

    async def upload_file(
        self,
        bucket: str,
        path: str,
        file_data: bytes,
        content_type: str = "application/octet-stream"
    ) -> str:
        """Upload a file to Supabase Storage."""
        self.client.storage.from_(bucket).upload(
            path,
            file_data,
            {"content-type": content_type}
        )
        return f"{bucket}/{path}"

    def get_public_url(self, bucket: str, path: str) -> str:
        """Get public URL for a file."""
        return self.client.storage.from_(bucket).get_public_url(path)

    def get_signed_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Get signed URL for private file."""
        return self.client.storage.from_(bucket).create_signed_url(path, expires_in)["signedURL"]


# Singleton instance
_supabase: Optional[SupabaseClient] = None

def get_supabase() -> SupabaseClient:
    global _supabase
    if _supabase is None:
        _supabase = SupabaseClient()
    return _supabase
```

### 0.5 Channel Abstraction Layer

```python
# integrations/channels/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class Message:
    """Platform-agnostic message format."""
    id: str
    channel_id: str
    user_id: str
    content: str
    attachments: List[Dict] = None
    thread_id: Optional[str] = None
    metadata: Dict[str, Any] = None

@dataclass
class User:
    """Platform-agnostic user format."""
    id: str
    name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    slack_id: Optional[str] = None

class ChannelAdapter(ABC):
    """Base adapter for all channel integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name identifier."""
        pass

    @abstractmethod
    async def send_message(
        self,
        channel_id: str,
        content: str,
        attachments: List[Dict] = None,
        thread_id: Optional[str] = None
    ) -> Message:
        """Send a message."""
        pass

    @abstractmethod
    async def update_message(
        self,
        channel_id: str,
        message_id: str,
        content: str
    ) -> Message:
        """Update an existing message."""
        pass

    @abstractmethod
    async def upload_file(
        self,
        channel_id: str,
        file_data: bytes,
        filename: str,
        title: Optional[str] = None
    ) -> str:
        """Upload a file and return URL."""
        pass

    @abstractmethod
    async def get_user(self, user_id: str) -> User:
        """Get user information."""
        pass

    @abstractmethod
    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        reaction: str
    ) -> bool:
        """Add a reaction to a message."""
        pass


# integrations/channels/slack_adapter.py

from slack_sdk import WebClient
from .base import ChannelAdapter, Message, User

class SlackAdapter(ChannelAdapter):
    """Slack-specific implementation."""

    def __init__(self, bot_token: str):
        self.client = WebClient(token=bot_token)

    @property
    def name(self) -> str:
        return "slack"

    async def send_message(
        self,
        channel_id: str,
        content: str,
        attachments: List[Dict] = None,
        thread_id: Optional[str] = None
    ) -> Message:
        response = self.client.chat_postMessage(
            channel=channel_id,
            text=content,
            blocks=attachments,
            thread_ts=thread_id
        )
        return Message(
            id=response["ts"],
            channel_id=channel_id,
            user_id="bot",
            content=content,
            thread_id=thread_id
        )

    # ... rest of implementation


# integrations/channels/web_adapter.py

from .base import ChannelAdapter, Message, User

class WebAdapter(ChannelAdapter):
    """Web UI implementation via WebSocket/SSE."""

    def __init__(self, websocket_manager):
        self.ws = websocket_manager

    @property
    def name(self) -> str:
        return "web"

    async def send_message(
        self,
        channel_id: str,  # conversation_id for web
        content: str,
        attachments: List[Dict] = None,
        thread_id: Optional[str] = None
    ) -> Message:
        message = Message(
            id=str(uuid.uuid4()),
            channel_id=channel_id,
            user_id="assistant",
            content=content,
            attachments=attachments
        )
        await self.ws.broadcast(channel_id, message)
        return message

    # ... rest of implementation


# integrations/channels/router.py

class ChannelRouter:
    """Routes messages to appropriate channel adapters."""

    def __init__(self):
        self.adapters: Dict[str, ChannelAdapter] = {}

    def register(self, adapter: ChannelAdapter):
        self.adapters[adapter.name] = adapter

    def get(self, channel_type: str) -> ChannelAdapter:
        if channel_type not in self.adapters:
            raise ValueError(f"No adapter for: {channel_type}")
        return self.adapters[channel_type]

# Usage in main.py
router = ChannelRouter()
router.register(SlackAdapter(os.getenv("SLACK_BOT_TOKEN")))
router.register(WebAdapter(websocket_manager))
```

---

## Phase 1: Expand mockup-studio → unified-ui

### 1.1 Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Frontend** | Vanilla JS + HTML/CSS | Keep existing mockup-studio stack, no framework migration |
| **Styling** | CSS Variables (Cosmic Theme) | Already implemented in mockup-studio |
| **Local Server** | Express.js | Existing server.js for local dev |
| **Auth** | Supabase Auth (prod) / FastAPI simple auth (dev) | Flexible deployment |
| **Backend** | FastAPI | ALL business logic, chat, AI calls go through here |
| **Deployment** | Static hosting (prod) / Express (dev) | Simple, fast |

### 1.2 Implementation Steps

1. **Rename mockup-studio → unified-ui**
2. **Add MMG landing page** with modern company branding
3. **Add auth layer** (Supabase prod, simple local dev)
4. **Add sidebar navigation** with tool switching + settings dropdowns
5. **Add chat interface** (ChatGPT-style, calls FastAPI)
6. **Refactor mockup-studio as a "tool"** within the sidebar
7. **Add FastAPI chat endpoints** for AI communication

### 1.3 FastAPI Endpoints for Unified UI

```python
# api/server.py - New endpoints for unified UI

# ============================================
# AUTH ENDPOINTS (for local dev / Supabase validation)
# ============================================
POST /api/auth/login          # Validate credentials, return token + user + roles
POST /api/auth/logout         # Invalidate session
GET  /api/auth/me             # Get current user info and roles

# ============================================
# CHAT ENDPOINTS (Slack replacement)
# ============================================
POST /api/chat/message        # Send message, get streaming AI response (SSE)
GET  /api/chat/conversations  # List user's conversations
GET  /api/chat/conversation/{id}  # Get conversation with messages
POST /api/chat/conversation   # Create new conversation
DELETE /api/chat/conversation/{id}  # Delete conversation

# ============================================
# EXISTING MOCKUP ENDPOINTS (already work)
# ============================================
# /api/mockup/* - All existing endpoints continue to work

# ============================================
# PROPOSAL ENDPOINTS
# ============================================
POST /api/proposals/generate  # Generate proposal (same as chat tool call)
GET  /api/proposals/history   # User's proposal history

# ============================================
# BO ENDPOINTS (role-based)
# ============================================
GET  /api/bo/pending          # Get BOs pending user's action (based on roles)
POST /api/bo/{id}/approve     # Approve BO
POST /api/bo/{id}/reject      # Reject BO with reason
```

### 1.4 Design System (Cosmic Theme)

Already implemented in mockup-studio:

```css
:root {
  /* Void - Base blacks */
  --void-pure: #000000;
  --void-deep: #020204;
  --void-base: #08080c;
  --void-surface: #121218;
  --void-hover: #18181f;

  /* Quantum - Primary */
  --quantum-500: #3381ff;

  /* Plasma - Secondary */
  --plasma-500: #06b6d4;

  /* Nebula - Accent */
  --nebula-500: #a855f7;

  /* Gradients */
  --gradient-quantum: linear-gradient(135deg, var(--quantum-500), var(--plasma-500), var(--nebula-500));
}
```

---

## Phase 2: Feature Migration

### 2.1 Chat Interface
- Port `core/llm.py` conversation loop to work with web
- Streaming responses via Server-Sent Events
- Tool results displayed inline (mockups, proposals, BOs)
- Conversation history persisted to Supabase

### 2.2 Mockup Studio Integration
- Port canvas editor from mockup-studio
- Embed as side panel tool
- Direct integration with chat ("make this mockup brighter")

### 2.3 Proposal Builder
- Visual proposal configuration
- Real-time preview
- Direct chat integration

### 2.4 BO Workflow
- Web-based approval interface
- Same multi-stage flow
- Slack notifications still work

---

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **Phase 0** | 1-2 weeks | Supabase setup, schema migration, channel abstraction |
| **Phase 1** | 2-3 weeks | Next.js shell, auth, basic chat interface |
| **Phase 2** | 2-3 weeks | Tool integrations, Mockup Studio port |
| **Phase 3** | 1-2 weeks | Polish, testing, migration |

**Total: 6-10 weeks**

---

## Cost Estimate

### Infrastructure

| Service | Current | With Supabase |
|---------|---------|---------------|
| Render (bot) | $7/mo | $7/mo (keep for Python backend) |
| Render (disk) | $3/mo | $0 (use Supabase Storage) |
| Supabase | $0 | $0 free tier → $25/mo Pro |
| Vercel | $0 | $0 free tier → $20/mo Pro |
| **Total** | ~$10/mo | ~$10-52/mo |

---

## Next Steps

1. **Create Supabase project**
2. **Run schema migrations**
3. **Migrate existing SQLite data**
4. **Update Python backend to use Supabase client**
5. **Test Slack bot still works**
6. **Begin Next.js frontend**

---

*Document Version: 3.0*
*Last Updated: December 4, 2024*
*Author: Claude (AI Assistant)*

### Changelog

**v3.0** - Added unified-ui architecture:
- Key architecture principles (FastAPI-only communication)
- Sales Department module with multi-role support (sales_person, hos, admin)
- Single sidebar with tool switching + settings dropdowns
- Expand mockup-studio → unified-ui approach (vanilla JS, not framework migration)
- FastAPI endpoints for chat, auth, proposals, BOs
- Updated directory structure
