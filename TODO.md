# Sales Proposals Bot - TODO

## Phase 1: Refactoring

- [x] Complete initial refactor (fix remaining import issues)
- [x] Further refactor and decouple long scripts (prompts, parsing logic, etc.)
- [x] Decouple pre/post image modifications in mockup generator for easier customization
  - Created `generators/effects/` module with modular, configurable effects
  - `EffectConfig` dataclass for all parameters
  - Separate classes: `EdgeCompositor`, `DepthEffect`, `VignetteEffect`, `ShadowEffect`, `ColorAdjustment`, `ImageBlur`, `Sharpening`, `OverlayBlending`
- [x] Create centralized AI provider abstraction layer
  - Created `integrations/llm/` module with `LLMClient` unified interface
  - Abstract base classes in `base.py`
  - OpenAI provider implementation in `providers/openai.py`
  - Prompts organized in `prompts/` directory
  - JSON schemas in `schemas/` directory
  - [ ] Migrate image generation from GPT-image-1 to Google Nano Banana 2
- [x] Centralize memory management (`utils/memory.py`)
- [x] Create task queue for mockup generation (`utils/task_queue.py`)

## Phase 2: Features

- [x] Add currency conversion to sales proposals

## Phase 3: Documentation

- [x] Add comprehensive documentation
  - Created `ARCHITECTURE.md` with full technical documentation
  - Project structure, core architecture, module deep dives
  - Data flow diagrams, database schema, configuration system
  - LLM integration patterns, deployment setup, troubleshooting

## Phase 4: Frontend

- [ ] Finish new frontend
  - [ ] All existing features/functionality from current frontend
  - [ ] Native zoom in/out for template editing
  - [ ] Template editing for bad/incorrect templates
  - [ ] Visual template picker in generate mode (preview before selecting)
  - [ ] Pixel enhancer tool
- [ ] Migrate to new frontend

## Phase 5: Templates

- [ ] Fix currently broken location templates
- [ ] Add new location templates

## Phase 6: Booking Order Flow

- [ ] Finish BO flow (Note: Must align on requirements/demands first before implementation)
