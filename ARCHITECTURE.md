# Sales Proposal Bot - Technical Architecture

A comprehensive technical guide for engineers working on the BackLite Media Sales Proposal Bot codebase.

---

## Table of Contents

- [Overview](#overview)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Core Architecture](#core-architecture)
- [Module Deep Dives](#module-deep-dives)
- [Data Flow](#data-flow)
- [Database Schema](#database-schema)
- [Configuration System](#configuration-system)
- [LLM Integration](#llm-integration)
- [Deployment](#deployment)
- [Development Setup](#development-setup)
- [Key Patterns & Conventions](#key-patterns--conventions)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Sales Proposal Bot is an AI-powered Slack bot that automates sales operations for BackLite Media, an outdoor advertising company. It handles:

1. **Proposal Generation** - Creates branded PowerPoint/PDF financial proposals
2. **Mockup Visualization** - Composites creative images onto billboard photos
3. **Booking Order Workflow** - Multi-stage approval pipeline for booking orders

The system is built on FastAPI, uses OpenAI GPT-5 for conversation and reasoning, and deploys to Render.com with a persistent disk for templates and data storage.

---

## Technology Stack

### Backend
| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Framework | FastAPI + Uvicorn | Async HTTP server, Slack webhooks |
| LLM Provider | OpenAI GPT-5 | Conversation, reasoning, function calling |
| Image Generation | OpenAI gpt-image-1 | AI-generated mockup creatives |
| Database | SQLite | Proposals, BOs, costs, mockup frames |
| Document Generation | python-pptx | PowerPoint slide creation |
| PDF Conversion | LibreOffice (headless) | PPTX to PDF conversion |
| Image Processing | OpenCV, Pillow, NumPy | Mockup compositing, perspective warping |
| Slack SDK | slack-sdk | Bot messaging, file uploads, events |

### Frontend (Auxiliary Services)
| Service | Technology | Purpose |
|---------|------------|---------|
| Cost Dashboard | Express.js + Vanilla JS | AI cost analytics visualization |
| Mockup Studio | React + Node.js | Billboard photo/frame editor (WIP) |

### Infrastructure
| Component | Technology |
|-----------|------------|
| Hosting | Render.com |
| Container | Docker (Python 3.11 + LibreOffice) |
| Storage | Render Disk (/data volume, 5GB) |
| CI/CD | GitHub → Render auto-deploy |

---

## Project Structure

```
Sales Proposals/
├── main.py                    # Entry point - uvicorn startup
├── config.py                  # Central configuration hub (21KB)
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Production container
├── render.yaml               # Render.com deployment config
│
├── api/
│   └── server.py             # FastAPI app, Slack event handler, lifecycle
│
├── core/
│   ├── llm.py                # Main conversation loop (1200+ lines)
│   ├── proposals.py          # Proposal generation logic
│   └── tools.py              # LLM function/tool definitions
│
├── db/
│   ├── database.py           # SQLite schema & ORM operations
│   └── cache.py              # In-memory session caches
│
├── generators/
│   ├── mockup.py             # Mockup generation engine
│   ├── pptx.py               # PowerPoint slide generation
│   ├── pdf.py                # PDF conversion & merging
│   └── effects/              # Image processing effects module
│       ├── __init__.py       # Module exports
│       ├── config.py         # EffectConfig dataclass
│       ├── edge.py           # EdgeCompositor (anti-aliasing, blur)
│       ├── depth.py          # DepthEffect, VignetteEffect, ShadowEffect
│       ├── color.py          # ColorAdjustment, ImageBlur, Sharpening
│       └── compositor.py     # BillboardCompositor, warp_creative_to_billboard
│
├── integrations/
│   ├── llm/                  # LLM abstraction layer
│   │   ├── base.py           # Abstract base classes (LLMProvider, etc.)
│   │   ├── client.py         # LLMClient unified interface
│   │   ├── providers/
│   │   │   └── openai.py     # OpenAI implementation
│   │   ├── prompts/          # System prompts by domain
│   │   │   ├── chat.py       # Main conversation prompt
│   │   │   ├── bo_parsing.py # BO extraction prompt
│   │   │   ├── bo_editing.py # BO thread edit prompt
│   │   │   └── mockup.py     # AI creative generation prompt
│   │   └── schemas/          # JSON schemas for structured output
│   │       ├── bo_parsing.py
│   │       └── bo_editing.py
│   │
│   ├── openai/
│   │   └── cost_tracker.py   # Token cost calculation & tracking
│   │
│   └── slack/
│       ├── bo_messaging.py   # BO approval workflow messages
│       ├── file_utils.py     # File download, PDF validation
│       └── formatting.py     # SlackResponses helper class
│
├── routers/
│   ├── tool_router.py        # Routes LLM tool calls to handlers
│   ├── mockup_handler.py     # Mockup generation orchestration
│   └── file_classifier.py    # File type classification
│
├── workflows/
│   ├── bo_parser.py          # BookingOrderParser class
│   └── bo_approval.py        # BO approval state machine
│
├── utils/
│   ├── memory.py             # Centralized GC & memory management
│   └── task_queue.py         # MockupTaskQueue (concurrency limiter)
│
├── bo_templates/             # BO Excel templates
│   ├── backlite_bo_template.xlsx
│   └── viola_bo_template.xlsx
│
├── render_main_data/         # Development data directory
│   ├── templates/            # PPTX templates (25+ locations)
│   ├── mockups/              # Mockup photos & generated images
│   ├── Sofia-Pro Font/       # Custom brand fonts
│   └── currency_config.json  # Multi-currency settings
│
├── dashboard/                # Cost analytics dashboard
│   ├── server.js
│   └── public/
│
└── mockup-studio/            # Mockup editor (React)
    ├── server.js
    └── public/
```

---

## Core Architecture

### Request Flow

```
┌─────────────────┐
│  Slack Message  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  api/server.py  │────▶│ Signature Verify │
│  POST /slack/   │     └──────────────────┘
│    events       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  core/llm.py    │────▶│  User History    │
│  main_llm_loop  │     │  (db/cache.py)   │
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐
│ LLMClient       │
│ (GPT-5 + tools) │
└────────┬────────┘
         │
         ├──────────────────────┬────────────────────┐
         ▼                      ▼                    ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Tool: Proposals │   │ Tool: Mockup    │   │ Tool: BO Parse  │
│ routers/tool_   │   │ routers/mockup_ │   │ workflows/      │
│ router.py       │   │ handler.py      │   │ bo_parser.py    │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ generators/     │   │ generators/     │   │ workflows/      │
│ pptx.py, pdf.py │   │ mockup.py       │   │ bo_approval.py  │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Slack Response                           │
│                (files, messages, buttons)                   │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `api/server.py` | HTTP endpoint, Slack signature verification, lifecycle management |
| `core/llm.py` | Conversation orchestration, user context, tool call routing |
| `core/tools.py` | Tool definitions (JSON schema for LLM function calling) |
| `routers/tool_router.py` | Dispatch tool calls to appropriate handlers |
| `generators/*` | Content generation (PPTX, PDF, mockups) |
| `workflows/*` | Business process state machines (BO approval) |
| `integrations/llm/*` | Provider-agnostic LLM abstraction |
| `db/*` | Data persistence and caching |
| `utils/*` | Cross-cutting utilities (memory, queuing) |

---

## Module Deep Dives

### config.py - Configuration Hub

The central configuration module handles:

1. **Environment Detection**
   ```python
   # Production uses /data volume, development uses local paths
   if os.path.exists("/data/"):
       TEMPLATES_DIR = Path("/data/templates")
   else:
       TEMPLATES_DIR = Path(__file__).parent / "render_main_data" / "templates"
   ```

2. **Template Discovery**
   - Scans `TEMPLATES_DIR` for `.pptx` files
   - Extracts metadata from `metadata.txt` files per location
   - Creates normalized location keys (e.g., "UAE 03" → "uae_03_pptx")

3. **Currency System**
   - Loads `currency_config.json` with exchange rates (AED as base)
   - `convert_currency_value(amount, from_currency, to_currency)`
   - `format_currency_value(amount, currency)` - locale-aware formatting

4. **Location Metadata**
   ```python
   LOCATION_METADATA = {
       "landmark": {
           "display_name": "The Landmark",
           "upload_fee": 5000,
           "series": "Digital",
           "height": "10m",
           "width": "30m",
           "number_of_faces": 3,
           "display_type": "LED",
           "spot_duration": "15",
           "loop_duration": "90"
       }
   }
   ```

5. **Permission Checks**
   - `is_admin(user_id)` - Checks against `hos_config.json`
   - `can_manage_locations(user_id)` - Location CRUD permissions

### core/llm.py - Conversation Engine

The main LLM loop (1200+ lines) orchestrates all user interactions:

```python
async def main_llm_loop(channel: str, user_id: str, user_input: str, event: dict):
    """
    Main entry point for all user messages.

    1. Retrieve/create user conversation history
    2. Build messages array with system prompt + history
    3. Call LLM with tools
    4. Handle tool calls (proposals, mockups, BOs)
    5. Post response to Slack
    6. Update conversation history
    """
```

**Key Features:**
- Conversation history per user (expires after 1 hour)
- Multi-turn context awareness
- File attachment handling (images, PDFs, Excel)
- Tool call iteration (LLM can call multiple tools sequentially)
- Error recovery with user-friendly messages

### generators/effects/ - Image Processing Module

Modular, configurable image effects for billboard mockup compositing:

```
EffectConfig (config.py)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│              BillboardCompositor                      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │EdgeCompositor│  │DepthEffect  │  │ColorAdjustment│ │
│  │- anti-alias │  │- night glow │  │- brightness  │ │
│  │- gamma blur │  │- day haze   │  │- contrast    │ │
│  │- feathering │  └─────────────┘  │- saturation  │ │
│  │- contact    │                   │- temperature │ │
│  │  shadow     │  ┌─────────────┐  └──────────────┘ │
│  └─────────────┘  │VignetteEffect│                   │
│                   │ShadowEffect │                   │
│                   └─────────────┘                   │
└──────────────────────────────────────────────────────┘
```

**Usage:**
```python
from generators.effects import warp_creative_to_billboard, EffectConfig

# Simple usage with defaults
result = warp_creative_to_billboard(
    billboard_image,
    creative_image,
    frame_points,  # 4 corner coordinates
    config={"edgeBlur": 12, "brightness": 110},
    time_of_day="night"
)

# Advanced usage
config = EffectConfig(
    edge_blur=15,
    edge_smoother=4,  # 4x MSAA
    depth_multiplier=20,
    brightness=105,
    contrast=95
)
compositor = BillboardCompositor(config, time_of_day="night")
result = compositor.composite(billboard, creative, frame_points)
```

### workflows/bo_parser.py - Booking Order Processing

Parses uploaded BO documents using LLM-powered extraction:

```python
class BookingOrderParser:
    async def parse_booking_order(self, file_path, file_type, company_name):
        """
        1. Classify BO type (Backlite vs Viola)
        2. Extract text/tables from PDF
        3. Use LLM with JSON schema to extract structured data
        4. Generate standardized Excel output
        5. Return parsed data with warnings
        """
```

**Extracted Data Structure:**
```python
{
    "bo_number": "BO-2025-001",
    "bo_date": "2025-12-01",
    "client": "Nike Middle East",
    "brand_campaign": "Air Max 2025",
    "category": "DOOH",
    "locations": [
        {
            "location_name": "The Landmark",
            "location_key": "landmark",
            "net_amount": 1500000,
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        }
    ],
    "municipality_fee": 10000,
    "production_upload_fee": 5000,
    "net_pre_vat": 1515000,
    "vat_rate": 5,
    "vat_value": 75750,
    "gross_amount": 1590750,
    "currency": "AED",
    "payment_terms": "50% advance, 50% on completion"
}
```

### utils/task_queue.py - Concurrency Management

Prevents memory exhaustion during mockup generation:

```python
class MockupTaskQueue:
    def __init__(self, max_concurrent: int = 3):
        """Limits concurrent mockup generations to prevent OOM."""

    async def submit(self, func: Callable, *args, **kwargs) -> Any:
        """
        Submit task to queue.
        - If slots available: execute immediately
        - If queue full: wait for slot (max 30s to start, 10min to complete)
        - Automatic memory cleanup after each task
        """

# Global instance
mockup_queue = MockupTaskQueue(max_concurrent=3)

# Usage
result = await mockup_queue.submit(generate_mockup_func, location, creative)
```

### utils/memory.py - Memory Management

Centralized garbage collection (prevents scattered `gc.collect()` calls):

```python
def cleanup_memory(
    context: Optional[str] = None,  # For logging
    aggressive: bool = False,        # Full 3-gen GC + malloc_trim
    log_stats: bool = True           # Log before/after memory
) -> dict:
    """
    Single point of control for memory cleanup.

    Returns: {"before": {...}, "after": {...}, "freed_mb": float}
    """
```

---

## Data Flow

### Proposal Generation Flow

```
User: "make me a landmark proposal, 2 weeks, 1.5M, client Nike"
                    │
                    ▼
┌───────────────────────────────────────┐
│ main_llm_loop() receives message      │
│ - Adds to conversation history        │
│ - Builds messages with system prompt  │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ LLMClient.complete() with tools       │
│ - GPT-5 analyzes request              │
│ - Returns tool_call: get_separate_    │
│   proposals with arguments            │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ handle_tool_call() dispatches to      │
│ process_proposals()                   │
│ - Validates location exists           │
│ - Calculates fees (upload for digital)│
│ - Calculates VAT (5%)                 │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ generators/pptx.py                    │
│ - Loads location PPTX template        │
│ - Fills in proposal data              │
│ - Creates duration/rate table         │
│ - Saves individual PPTX               │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ generators/pdf.py                     │
│ - Converts PPTX → PDF via LibreOffice │
│ - Merges multiple PDFs if needed      │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ Upload to Slack + Log to database     │
│ - Files uploaded to channel           │
│ - Entry added to proposals_log table  │
│ - Confirmation message sent           │
└───────────────────────────────────────┘
```

### Mockup Generation Flow

```
User: [uploads image] "mockup for landmark"
                    │
                    ▼
┌───────────────────────────────────────┐
│ main_llm_loop() detects file + request│
│ - Downloads file from Slack           │
│ - Stores in mockup_history cache      │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ LLM returns: generate_mockup tool     │
│ - location_key: "landmark"            │
│ - time_of_day: "day" (or specified)   │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ handle_mockup_generation()            │
│ - Retrieves creative from cache       │
│ - Validates frame count matches       │
│ - Submits to task queue               │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ mockup_queue.submit()                 │
│ - Waits for available slot (max 3)    │
│ - Tracks memory usage                 │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ generators/mockup.py                  │
│ - Loads billboard photo               │
│ - Gets frame coordinates from DB      │
│ - Resizes creative to fit             │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ generators/effects/compositor.py      │
│ - Perspective warp (cv2.warpPerspective)
│ - Edge anti-aliasing (4x supersample) │
│ - Gamma-correct blur                  │
│ - Depth effects (night glow/day haze) │
│ - Color adjustments                   │
│ - Final composite                     │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ Save & Upload                         │
│ - cv2.imwrite() to temp file          │
│ - Upload to Slack                     │
│ - Log to mockup_usage table           │
│ - Cleanup memory                      │
└───────────────────────────────────────┘
```

### Booking Order Approval Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    BO APPROVAL WORKFLOW                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐                                             │
│  │Sales Person │                                             │
│  │uploads BO   │                                             │
│  └──────┬──────┘                                             │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────┐                                     │
│  │ Parse BO            │                                     │
│  │ - Classify type     │                                     │
│  │ - Extract data      │                                     │
│  │ - Generate Excel    │                                     │
│  └──────────┬──────────┘                                     │
│             │                                                │
│             ▼                                                │
│  ┌─────────────────────┐     ┌─────────────────────────┐    │
│  │ Sales Coordinator   │◀────│ pending_booking_orders  │    │
│  │ Reviews & Edits     │     │ cache stores BO data    │    │
│  └──────────┬──────────┘     └─────────────────────────┘    │
│             │                                                │
│     ┌───────┴───────┐                                        │
│     │               │                                        │
│     ▼               ▼                                        │
│ ┌────────┐    ┌──────────┐                                   │
│ │APPROVE │    │ REJECT   │                                   │
│ └────┬───┘    └────┬─────┘                                   │
│      │             │                                         │
│      │             ▼                                         │
│      │      ┌──────────────┐                                 │
│      │      │ Thread Edit  │                                 │
│      │      │ "change X"   │───┐                             │
│      │      └──────────────┘   │                             │
│      │             ▲           │                             │
│      │             └───────────┘                             │
│      │           (edit loop)                                 │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────────────┐                                     │
│  │ Head of Sales       │                                     │
│  │ Reviews             │                                     │
│  └──────────┬──────────┘                                     │
│             │                                                │
│     ┌───────┴───────┐                                        │
│     │               │                                        │
│     ▼               ▼                                        │
│ ┌────────┐    ┌──────────┐                                   │
│ │APPROVE │    │ REJECT   │──▶ Back to Coordinator           │
│ └────┬───┘    └──────────┘    with feedback                  │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────────────┐                                     │
│  │ Save to Database    │                                     │
│  │ Notify Finance      │                                     │
│  │ Send final PDF      │                                     │
│  └─────────────────────┘                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Tables

```sql
-- Proposal tracking
CREATE TABLE proposals_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submitted_by TEXT NOT NULL,           -- Slack user ID
    client_name TEXT NOT NULL,
    date_generated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    package_type TEXT,                     -- 'separate' or 'combined'
    locations TEXT,                        -- JSON array of location keys
    total_amount REAL,
    currency TEXT DEFAULT 'AED'
);

-- Mockup frame coordinates
CREATE TABLE mockup_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_key TEXT NOT NULL,
    time_of_day TEXT DEFAULT 'day',       -- 'day' or 'night'
    finish TEXT DEFAULT 'gold',           -- 'gold', 'matte', etc.
    photo_filename TEXT NOT NULL,
    frames_data TEXT NOT NULL,            -- JSON array of frame coordinates
    config_json TEXT,                     -- Per-frame effect config
    UNIQUE(location_key, time_of_day, finish, photo_filename)
);

-- Mockup usage analytics
CREATE TABLE mockup_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,
    location_key TEXT NOT NULL,
    time_of_day TEXT,
    finish TEXT,
    ai_prompt TEXT,                       -- NULL if uploaded creative
    creative_type TEXT,                   -- 'uploaded' or 'ai_generated'
    success BOOLEAN DEFAULT TRUE
);

-- Booking order storage
CREATE TABLE booking_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bo_ref TEXT UNIQUE NOT NULL,          -- Internal ref: bo_TIMESTAMP_COMPANY
    bo_number TEXT,                       -- Display number: DPD-XXX or VLA-XXX
    company TEXT NOT NULL,                -- 'Backlite' or 'Viola'
    client TEXT,
    original_file_path TEXT,
    parsed_excel_path TEXT,
    parsed_data TEXT,                     -- JSON blob of all extracted data
    approval_state TEXT,                  -- 'coordinator_review', 'hos_review', etc.
    submitted_by TEXT,
    approved_by_coordinator TEXT,
    approved_by_hos TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI API cost tracking
CREATE TABLE ai_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,
    model TEXT NOT NULL,                  -- 'gpt-5', 'gpt-image-1', etc.
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    cost_usd REAL NOT NULL,
    context TEXT                          -- What triggered this cost
);

-- Active BO approval workflows
CREATE TABLE bo_workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bo_ref TEXT UNIQUE NOT NULL,
    state TEXT NOT NULL,                  -- JSON blob of workflow state
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### In-Memory Caches (db/cache.py)

```python
# User conversation history - expires after 1 hour
user_history: Dict[str, List[dict]] = {}

# Uploaded creative files - expires after 30 minutes
mockup_history: Dict[str, dict] = {
    "user_id": {
        "creative_paths": [Path, Path, ...],
        "timestamp": datetime
    }
}

# Pending location template uploads - expires after 10 minutes
pending_location_additions: Dict[str, dict] = {}

# Active BO review sessions
pending_booking_orders: Dict[str, dict] = {
    "user_id": {
        "data": {...},
        "warnings": [...],
        "original_file_path": Path,
        "company": "Backlite",
        "approval_state": "coordinator_review",
        "timestamp": datetime
    }
}
```

---

## Configuration System

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-proj-...          # OpenAI API key
SLACK_BOT_TOKEN=xoxb-...            # Slack bot OAuth token
SLACK_SIGNING_SECRET=...            # Slack app signing secret

# Optional
OPENAI_MODEL=gpt-5                  # Default LLM model
PDF_CONVERT_CONCURRENCY=4           # Max concurrent PDF conversions
LOG_LEVEL=INFO                      # Logging verbosity
```

### Configuration Files

**hos_config.json** - Permissions & workflow routing
```json
{
  "admins": ["U12345678"],
  "coordinators": ["U87654321"],
  "head_of_sales": {
    "backlite": "U11111111",
    "viola": "U22222222"
  },
  "finance_channel": "C33333333"
}
```

**currency_config.json** - Multi-currency support
```json
{
  "base_currency": "AED",
  "currencies": {
    "AED": {"symbol": "AED", "rate": 1.0, "locale": "ar_AE"},
    "USD": {"symbol": "$", "rate": 0.272, "locale": "en_US"},
    "EUR": {"symbol": "EUR", "rate": 0.251, "locale": "de_DE"},
    "GBP": {"symbol": "GBP", "rate": 0.215, "locale": "en_GB"},
    "SAR": {"symbol": "SAR", "rate": 1.02, "locale": "ar_SA"}
  }
}
```

**Location metadata.txt** - Per-location template metadata
```
display_name=The Landmark
upload_fee=5000
series=Digital Premium
height=10m
width=30m
number_of_faces=3
display_type=LED
spot_duration=15
loop_duration=90
```

---

## LLM Integration

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LLMClient (Unified)                      │
│  - Provider-agnostic interface                              │
│  - Handles retries, rate limits                             │
│  - Cost tracking                                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Providers Layer                          │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ OpenAIProvider  │  │ AnthropicProvider│  (future)       │
│  │ - gpt-5         │  │ - claude-3      │                  │
│  │ - gpt-image-1   │  │ - claude-3.5    │                  │
│  │ - o1-preview    │  └─────────────────┘                  │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

### Usage Patterns

```python
from integrations.llm import LLMClient

# Initialize (uses config.py settings)
client = LLMClient.from_config()

# Simple completion
response = await client.complete(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)

# With function calling
response = await client.complete(
    messages=[...],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {...}
            }
        }
    ]
)

# With structured output (JSON schema)
response = await client.complete(
    messages=[...],
    json_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        }
    }
)

# File upload (for document analysis)
file_ref = await client.upload_file(path_to_pdf)
response = await client.complete(
    messages=[
        {"role": "user", "content": [
            {"type": "text", "text": "Summarize this document"},
            {"type": "file", "file_id": file_ref}
        ]}
    ]
)
await client.delete_file(file_ref)
```

### System Prompts

Located in `integrations/llm/prompts/`:

| File | Purpose | Key Elements |
|------|---------|--------------|
| `chat.py` | Main conversation | Available tools, location list, workflow instructions |
| `bo_parsing.py` | BO extraction | Field definitions, validation rules, output schema |
| `bo_editing.py` | Thread edits | Natural language → structured changes |
| `mockup.py` | AI creative | Billboard-optimized image generation |

---

## Deployment

### Docker Container

```dockerfile
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    libreoffice \
    libreoffice-writer \
    libreoffice-impress \
    fonts-liberation \
    fonts-dejavu \
    fontconfig

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . /app
WORKDIR /app

# Startup script handles:
# 1. Font installation from /data/Sofia-Pro Font
# 2. PYTHONPATH export
# 3. Uvicorn launch
CMD ["./start.sh"]
```

### Render.com Configuration (render.yaml)

```yaml
services:
  - type: web
    name: proposal-bot
    runtime: docker
    plan: starter
    healthCheckPath: /health
    envVars:
      - key: OPENAI_API_KEY
        sync: false
      - key: SLACK_BOT_TOKEN
        sync: false
      - key: SLACK_SIGNING_SECRET
        sync: false
    disk:
      name: data
      mountPath: /data
      sizeGB: 5

  - type: web
    name: ai-costs-dashboard
    runtime: node
    buildCommand: cd dashboard && npm install
    startCommand: cd dashboard && node server.js
    plan: starter
```

### Directory Structure (Production)

```
/data/                          # Render persistent disk
├── templates/                  # PPTX templates (synced from repo)
│   ├── The Landmark/
│   │   ├── template.pptx
│   │   └── metadata.txt
│   ├── Dubai Gateway/
│   └── ...
├── mockups/                    # Billboard photos & generated mockups
│   ├── landmark/
│   │   ├── day/
│   │   │   └── gold/
│   │   │       └── photo1.jpg
│   │   └── night/
│   └── ...
├── combined_bos/              # Generated BO Excel files
├── Sofia-Pro Font/            # Custom brand fonts
├── currency_config.json
├── hos_config.json
└── proposal_bot.db            # SQLite database
```

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for dashboard/mockup-studio)
- LibreOffice (for PDF conversion)
- OpenCV dependencies

### Local Setup

```bash
# Clone repository
git clone https://github.com/Amrtamer711/SalesProposalAI.git
cd SalesProposalAI

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install Python dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
OPENAI_API_KEY=sk-proj-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
EOF

# Run development server
python main.py
```

### Running Tests

```bash
# Unit tests
pytest tests/

# Integration tests (requires .env)
pytest tests/integration/ --env=.env

# Specific module
pytest tests/test_effects.py -v
```

### Code Quality

```bash
# Linting
ruff check .

# Type checking
mypy core/ generators/ integrations/

# Formatting
black .
```

---

## Key Patterns & Conventions

### Error Handling

```python
# Always catch and log, provide user-friendly message
try:
    result = await some_operation()
except Exception as e:
    logger.error(f"[MODULE] Operation failed: {e}")
    await slack_client.chat_postMessage(
        channel=channel,
        text="Sorry, something went wrong. Please try again."
    )
    return None
```

### Memory Management

```python
# After heavy operations (mockup generation, PDF conversion)
from utils.memory import cleanup_memory

try:
    result = heavy_operation()
finally:
    del large_array
    cleanup_memory(context="operation_name", aggressive=True)
```

### Async Patterns

```python
# Use asyncio.gather for parallel operations
results = await asyncio.gather(
    fetch_data_1(),
    fetch_data_2(),
    fetch_data_3()
)

# Use task queue for resource-intensive operations
from utils.task_queue import mockup_queue
result = await mockup_queue.submit(generate_mockup, location, creative)
```

### Logging Convention

```python
import logging
logger = logging.getLogger("proposal-bot")

# Format: [MODULE] Action description
logger.info(f"[MOCKUP] Generating mockup for {location}")
logger.error(f"[PROPOSAL] Failed to generate: {error}")
logger.debug(f"[LLM] Token usage: {tokens}")
```

### Configuration Access

```python
import config

# Environment-aware paths
templates_dir = config.TEMPLATES_DIR  # /data/templates or local
mockups_dir = config.MOCKUPS_DIR

# Location metadata
metadata = config.LOCATION_METADATA.get("landmark")

# Currency operations
converted = config.convert_currency_value(1000, "AED", "USD")
formatted = config.format_currency_value(1000, "AED")  # "AED 1,000"
```

---

## Troubleshooting

### Common Issues

**1. LibreOffice PDF conversion fails**
```
Error: LibreOffice not found
```
Solution: Ensure LibreOffice is installed and in PATH. On Docker, check Dockerfile includes `libreoffice` package.

**2. Memory exhaustion during mockup generation**
```
Error: Cannot allocate memory
```
Solution: Reduce `max_concurrent` in task queue, ensure `cleanup_memory()` called after operations.

**3. Slack signature verification fails**
```
Error: Invalid request signature
```
Solution: Verify `SLACK_SIGNING_SECRET` matches app settings. Check timestamp not too old (>5 min drift).

**4. Template not found**
```
Error: Location 'xyz' not found
```
Solution: Run `config.refresh_templates()` or restart server. Check template exists in TEMPLATES_DIR.

**5. Font rendering issues in PPTX**
```
Error: Font 'Sofia Pro' not found
```
Solution: Run `install_fonts.sh` or ensure fonts in `/data/Sofia-Pro Font/` and `fc-cache -fv` run.

### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG python main.py

# Check specific module
LOG_LEVEL=DEBUG python -c "from generators import mockup; ..."
```

### Health Checks

```bash
# API health
curl http://localhost:3000/health

# Database check
curl http://localhost:3000/api/db/status

# Template check
curl http://localhost:3000/api/templates/list
```

---

## Contributing

1. Create feature branch from `dev`
2. Make changes with tests
3. Run linting and type checks
4. Submit PR to `dev`
5. After review, merge to `dev`
6. Production deploys from `main` (merge `dev` → `main`)

### Branch Strategy

- `main` - Production (auto-deploys to Render)
- `dev` - Development/staging
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Oct 2025 | Initial release |
| 1.1 | Nov 2025 | LLM abstraction layer, effects module refactor |
| 1.2 | Dec 2025 | Multi-currency support, memory optimization |

---

**Last Updated:** December 2025
**Maintainer:** BackLite Media Engineering Team
