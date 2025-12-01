# Sales Proposals Bot - TODO

## Phase 1: Refactoring
- [ ] Complete initial refactor (fix remaining import issues)
- [ ] Further refactor and decouple long scripts (prompts, parsing logic, etc.)
- [ ] Decouple pre/post image modifications in mockup generator for easier customization
- [ ] Create centralized AI provider abstraction layer
  - [ ] Abstract API calls (different request/response structures per provider)
  - [ ] Centralized model configuration (swap models by changing config, not workflow code)
  - [ ] Migrate image generation from GPT-image-1 to Google Nano Banana 2

## Phase 2: Features
- [ ] Add currency conversion to sales proposals

## Phase 3: Documentation
- [ ] Add comprehensive documentation

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
