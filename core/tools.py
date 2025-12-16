"""
Tool definitions for the main LLM chat interface.
Centralized tool definitions using the unified ToolDefinition format.
"""

from typing import Union

from integrations.llm import RawTool, ToolDefinition


def get_base_tools() -> list[Union[ToolDefinition, RawTool]]:
    """Get base tools available to all users."""
    return [
        ToolDefinition(
            name="get_separate_proposals",
            description="Generate SEPARATE proposals - each location gets its own proposal slide with multiple duration/rate options. Use this when user asks to 'make', 'create', or 'generate' proposals for specific locations. Returns individual PPTs and combined PDF.",
            parameters={
                "type": "object",
                "properties": {
                    "proposals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description": "The location name - intelligently match to available locations. If user says 'gateway' or 'the gateway', match to 'dubai_gateway'. If user says 'jawhara', match to 'dubai_jawhara'. Use your best judgment to infer the correct location from the available list even if the name is abbreviated or has 'the' prefix."},
                                "start_date": {"type": "string", "description": "Start date for the campaign (e.g., 1st December 2025)"},
                                "end_date": {"type": "string", "description": "End date for the campaign. Either extract from user message if provided, or calculate from start_date + duration (e.g., start: 1st Dec + 4 weeks = end: 29th Dec). Use the first/shortest duration if multiple durations provided."},
                                "durations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of duration options (e.g., ['2 Weeks', '4 Weeks', '6 Weeks'])"
                                },
                                "net_rates": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of net rates corresponding to each duration (e.g., ['AED 1,250,000', 'AED 2,300,000', 'AED 3,300,000'])"
                                },
                                "spots": {"type": "integer", "description": "Number of spots (default: 1)", "default": 1},
                                "production_fee": {"type": "string", "description": "Production fee for static locations (e.g., 'AED 5,000'). If multiple production fees are mentioned (client changing artwork during campaign), sum them together (e.g., two productions at AED 20,000 each = 'AED 40,000'). Required for static locations."}
                            },
                            "required": ["location", "start_date", "end_date", "durations", "net_rates"]
                        },
                        "description": "Array of proposal objects. Each location can have multiple duration/rate options."
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client (required)"
                    },
                    "payment_terms": {
                        "type": "string",
                        "description": "Payment terms for the proposal (default: '100% upfront'). ALWAYS validate with user even if not explicitly mentioned. Examples: '100% upfront', '50% upfront, 50% on delivery', '30 days net'",
                        "default": "100% upfront"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency for displaying amounts (default: 'AED'). Use if user requests amounts in a different currency like 'USD', 'EUR', 'GBP', 'SAR', etc. The proposal will show all amounts converted to this currency with a note about the conversion.",
                        "default": "AED"
                    }
                },
                "required": ["proposals", "client_name", "payment_terms"]
            }
        ),
        ToolDefinition(
            name="get_combined_proposal",
            description="Generate COMBINED package proposal - all locations in ONE slide with single net rate. Use this when user asks for a 'package', 'bundle', or 'combined' deal with multiple locations sharing one total rate.",
            parameters={
                "type": "object",
                "properties": {
                    "proposals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description": "The location name - intelligently match to available locations. If user says 'gateway' or 'the gateway', match to 'dubai_gateway'. If user says 'jawhara', match to 'dubai_jawhara'. Use your best judgment to infer the correct location from the available list even if the name is abbreviated or has 'the' prefix."},
                                "start_date": {"type": "string", "description": "Start date for this location (e.g., 1st January 2026)"},
                                "end_date": {"type": "string", "description": "End date for this location. Either extract from user message if provided, or calculate from start_date + duration (e.g., start: 1st Jan + 2 weeks = end: 15th Jan)."},
                                "duration": {"type": "string", "description": "Duration for this location (e.g., '2 Weeks')"},
                                "spots": {"type": "integer", "description": "Number of spots (default: 1)", "default": 1},
                                "production_fee": {"type": "string", "description": "Production fee for static locations (e.g., 'AED 5,000'). If multiple production fees are mentioned (client changing artwork during campaign), sum them together (e.g., two productions at AED 20,000 each = 'AED 40,000'). Required for static locations."}
                            },
                            "required": ["location", "start_date", "end_date", "duration"]
                        },
                        "description": "Array of locations with their individual durations and start dates"
                    },
                    "combined_net_rate": {
                        "type": "string",
                        "description": "The total net rate for the entire package (e.g., 'AED 2,000,000')"
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Name of the client (required)"
                    },
                    "payment_terms": {
                        "type": "string",
                        "description": "Payment terms for the proposal (default: '100% upfront'). ALWAYS validate with user even if not explicitly mentioned. Examples: '100% upfront', '50% upfront, 50% on delivery', '30 days net'",
                        "default": "100% upfront"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency for displaying amounts (default: 'AED'). Use if user requests amounts in a different currency like 'USD', 'EUR', 'GBP', 'SAR', etc. The proposal will show all amounts converted to this currency with a note about the conversion.",
                        "default": "AED"
                    }
                },
                "required": ["proposals", "combined_net_rate", "client_name", "payment_terms"]
            }
        ),
        ToolDefinition(
            name="refresh_templates",
            description="Refresh the templates cache.",
            parameters={"type": "object", "properties": {}}
        ),
        ToolDefinition(
            name="edit_task_flow",
            description="Edit a task in the flow.",
            parameters={
                "type": "object",
                "properties": {
                    "task_number": {"type": "integer"},
                    "task_data": {"type": "object"}
                },
                "required": ["task_number", "task_data"]
            }
        ),
        ToolDefinition(
            name="add_location",
            description="Add a new location. Admin must provide ALL required metadata upfront. Digital locations require: sov, spot_duration, loop_duration, upload_fee. Static locations don't need these fields. ADMIN ONLY.",
            parameters={
                "type": "object",
                "properties": {
                    "location_key": {"type": "string", "description": "Folder/key name (lowercase, underscores for spaces, e.g., 'dubai_gateway')"},
                    "display_name": {"type": "string", "description": "Display name shown to users (e.g., 'The Dubai Gateway')"},
                    "display_type": {"type": "string", "enum": ["Digital", "Static"], "description": "Display type - determines which fields are required"},
                    "height": {"type": "string", "description": "Height with unit (e.g., '6m', '14m')"},
                    "width": {"type": "string", "description": "Width with unit (e.g., '12m', '7m')"},
                    "number_of_faces": {"type": "integer", "description": "Number of display faces (e.g., 1, 2, 4, 6)", "default": 1},
                    "series": {"type": "string", "description": "Series name (e.g., 'The Landmark Series', 'Digital Icons')"},
                    "sov": {"type": "string", "description": "Share of voice percentage - REQUIRED for Digital only (e.g., '16.6%', '12.5%')"},
                    "spot_duration": {"type": "integer", "description": "Duration of each spot in seconds - REQUIRED for Digital only (e.g., 10, 12, 16)"},
                    "loop_duration": {"type": "integer", "description": "Total loop duration in seconds - REQUIRED for Digital only (e.g., 96, 100)"},
                    "upload_fee": {"type": "integer", "description": "Upload fee in AED - REQUIRED for Digital only (e.g., 1000, 1500, 2000, 3000)"}
                },
                "required": ["location_key", "display_name", "display_type", "height", "width", "series"]
            }
        ),
        ToolDefinition(
            name="list_locations",
            description="ONLY call this when user explicitly asks to SEE or LIST available locations (e.g., 'what locations do you have?', 'show me locations', 'list all locations'). DO NOT call this when user mentions specific location names in a proposal request.",
            parameters={"type": "object", "properties": {}}
        ),
        ToolDefinition(
            name="delete_location",
            description="Delete an existing location (admin only, requires confirmation). ADMIN ONLY.",
            parameters={
                "type": "object",
                "properties": {
                    "location_key": {"type": "string", "description": "The location key or display name to delete"}
                },
                "required": ["location_key"]
            }
        ),
        ToolDefinition(
            name="export_proposals_to_excel",
            description="Export all proposals from the backend database to Excel and send to user. ADMIN ONLY.",
            parameters={"type": "object", "properties": {}}
        ),
        ToolDefinition(
            name="get_proposals_stats",
            description="Get summary statistics of proposals from the database",
            parameters={"type": "object", "properties": {}}
        ),
        ToolDefinition(
            name="export_booking_orders_to_excel",
            description="Export all booking orders from the backend database to Excel and send to user. Shows BO ref, client, campaign, gross total, status, dates, etc. ADMIN ONLY.",
            parameters={"type": "object", "properties": {}}
        ),
        ToolDefinition(
            name="fetch_booking_order",
            description="Fetch a booking order by its BO number from the original document (e.g., BL-001, VL-042, ABC123, etc). This is the BO number that appears in the client's booking order document. Returns the BO data and combined PDF file. If the BO exists but was created with outdated schema/syntax, it will be automatically regenerated with the latest format. ADMIN ONLY.",
            parameters={
                "type": "object",
                "properties": {
                    "bo_number": {"type": "string", "description": "The booking order number from the original document (e.g., 'BL-001', 'VL-042', 'ABC123')"}
                },
                "required": ["bo_number"]
            }
        ),
        ToolDefinition(
            name="revise_booking_order",
            description="Start a revision workflow for an existing booking order. Sends the BO to Sales Coordinator for edits, then through the full approval flow (Coordinator → HoS → Finance). Use this when admin wants to revise/update an already submitted BO. ADMIN ONLY.",
            parameters={
                "type": "object",
                "properties": {
                    "bo_number": {"type": "string", "description": "The booking order number to revise (e.g., 'DPD-112652', 'VLA-001')"}
                },
                "required": ["bo_number"]
            }
        ),
        ToolDefinition(
            name="generate_mockup",
            description="Generate a billboard mockup. IMPORTANT: If user uploads image file(s) and mentions a location for mockup, call this function IMMEDIATELY - do not ask for clarification. User can upload image(s) OR provide AI prompt(s) for generation OR reuse creatives from recent mockup (within 30 min) by just specifying new location. System stores creative files for 30 minutes enabling follow-up requests on different locations. For AI generation: ALWAYS use 1 prompt (single array entry) unless user EXPLICITLY requests multiple frames (e.g., '3-frame mockup', 'show evolution'). 1 creative = tiled across all frames, N creatives = matched 1:1 to N frames. System validates frame count compatibility automatically. Billboard variations can be specified with time_of_day (day/night/all) and finish (gold/silver/all). Use 'all' or omit to randomly select from all available variations.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The location name - intelligently match to available locations. If user says 'gateway' or 'the gateway', match to 'dubai_gateway'. If user says 'jawhara', match to 'dubai_jawhara'. Use your best judgment to infer the correct location from the available list."},
                    "time_of_day": {"type": "string", "description": "Optional time of day: 'day', 'night', or 'all' (default). Use 'all' for random selection from all time variations.", "enum": ["day", "night", "all"]},
                    "finish": {"type": "string", "description": "Optional billboard finish: 'gold', 'silver', or 'all' (default). Use 'all' for random selection from all finish variations.", "enum": ["gold", "silver", "all"]},
                    "ai_prompts": {"type": "array", "items": {"type": "string"}, "description": "Optional array of DETAILED AI prompts to generate billboard-ready ARTWORK. Each prompt generates one creative image. CRITICAL PROMPT QUALITY RULES: Each prompt MUST be comprehensive and detailed (minimum 2-3 sentences), including: specific product/brand name, visual elements, colors, mood/atmosphere, composition details, text/slogans, and any specific details user mentioned. DO NOT use vague 1-2 word descriptions. ALWAYS default to 1 prompt unless user EXPLICITLY requests multiple frames (e.g., '3-frame mockup', 'show evolution'). If 1 prompt: tiled across all frames. If N prompts: matched 1:1 to N frames. GOOD examples: ['Luxury Rolex watch advertisement featuring gold Submariner model on black velvet surface, dramatic spotlight creating reflections, \"Timeless Elegance\" text in elegant serif font, Rolex crown logo prominent'] (single frame - tiled), or ['Mercedes-Benz S-Class sedan front 3/4 view on wet asphalt with city lights bokeh background, sleek silver paint, dramatic evening lighting, \"The Best or Nothing\" slogan', 'Mercedes interior shot showing leather seats and dashboard technology, ambient lighting, sophisticated luxury atmosphere', 'Mercedes driving on mountain road at sunset, dynamic motion blur, aspirational lifestyle imagery'] (3-frame evolution). BAD examples: ['watch ad'], ['car', 'interior', 'driving']. [] means user uploads images."}
                },
                "required": ["location"]
            }
        ),
        ToolDefinition(
            name="parse_booking_order",
            description="Parse a booking order document (Excel, PDF, or image) for Backlite or Viola. Available to ALL users. Extracts client, campaign, locations, pricing, dates, and financial data. Infer the company from document content (e.g., letterhead, branding, or 'BackLite'/'Viola' text) - default to 'backlite' if unclear. Biased toward classifying uploads as ARTWORK unless clearly a booking order.",
            parameters={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "enum": ["backlite", "viola"],
                        "description": "Company name - either 'backlite' or 'viola'. Infer from document branding/letterhead. Default to 'backlite' if unclear."
                    },
                    "user_notes": {
                        "type": "string",
                        "description": "Optional notes or instructions from user about the booking order"
                    }
                },
                "required": ["company"]
            }
        ),
        # OpenAI code_interpreter - allows model to execute code
        RawTool(raw={"type": "code_interpreter", "container": {"type": "auto"}}),
    ]


def get_admin_tools() -> list[ToolDefinition]:
    """Get additional tools available only to admins."""
    return []
