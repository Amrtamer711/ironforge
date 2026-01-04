"""
Chat Router for Video Critique.

Handles web chat endpoints for the unified-ui integration.
Native implementation following sales-module patterns.

User Identity:
- Uses TrustedUserMiddleware from crm-security for authentication
- AuthUser injected via Depends(require_permission(...))
- user.id, user.email, user.name, user.companies, user.permissions available
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from crm_security import require_permission, AuthUser, has_permission

import config
from core.llm import main_llm_loop, get_conversation_state, clear_conversation_state
from handlers.tool_router import ToolRouter
from integrations.channels import get_channel
from core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_MESSAGE_LENGTH = 10_000


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """Chat message request."""
    message: str = Field(..., description="User message")
    session_id: str | None = Field(None, description="Session ID for conversation continuity")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters allowed.")
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v


class ChatResponse(BaseModel):
    """Chat message response."""
    response: str = Field(..., description="Assistant response")
    session_id: str = Field(..., description="Session ID")
    timestamp: str = Field(..., description="Response timestamp")


class ChatSession(BaseModel):
    """Chat session info."""
    session_id: str
    created_at: str
    message_count: int


class ClearSessionResponse(BaseModel):
    """Clear session response."""
    success: bool
    message: str


class ActionRequest(BaseModel):
    """Interactive action request (button clicks, approvals)."""
    action_id: str = Field(..., description="Action identifier (e.g., approve_reviewer)")
    workflow_id: str = Field(..., description="Workflow ID to act on")


class ActionResponse(BaseModel):
    """Response from an interactive action."""
    success: bool
    message: str
    requires_form: bool = False
    form_type: str | None = None
    workflow_id: str | None = None


class FormSubmission(BaseModel):
    """Form/modal submission (rejection reason, etc.)."""
    form_type: str = Field(..., description="Type of form (rejection, return)")
    workflow_id: str = Field(..., description="Workflow ID")
    category: str | None = Field(None, description="Rejection/return category")
    reason: str | None = Field(None, description="Detailed reason")


class CommandRequest(BaseModel):
    """Slash command equivalent request."""
    command: str = Field(..., description="Command name (log, edit, delete, recent)")
    args: str | None = Field(None, description="Command arguments")
    session_id: str | None = Field(None, description="Session ID")


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================

@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    user: AuthUser = Depends(require_permission("video:chat:use")),
):
    """
    Send a chat message and get a response.
    Requires video:chat:use permission.
    """
    session_id = request.session_id or str(uuid.uuid4())

    logger.info(f"[Chat] Message from {user.email}: {request.message[:50]}...")

    try:
        tool_router = ToolRouter()

        response = await main_llm_loop(
            channel_id=session_id,
            user_id=user.id,
            user_input=request.message,
            image_data=None,
            channel=None,
            user_name=user.name or user.email,
            user_email=user.email,
            user_companies=user.companies,
            tool_router=tool_router,
        )

        logger.info(f"[Chat] Response generated for {user.email}")

        return ChatResponse(
            response=response,
            session_id=session_id,
            timestamp=datetime.now(config.UAE_TZ).isoformat(),
        )

    except Exception as e:
        logger.error(f"[Chat] Error processing message for {user.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message/stream")
async def send_message_stream(
    request: ChatRequest,
    user: AuthUser = Depends(require_permission("video:chat:use")),
):
    """
    Send a chat message and stream the response via SSE.
    Requires video:chat:use permission.
    """
    session_id = request.session_id or str(uuid.uuid4())

    async def generate():
        try:
            from integrations.llm import LLMClient, LLMMessage
            from integrations.llm.prompts import create_design_request_system_prompt
            from core.tools import get_tool_definitions

            state = get_conversation_state(user.id)

            system_prompt = create_design_request_system_prompt(user.name or user.email)
            messages = [
                LLMMessage.system(system_prompt),
                *[LLMMessage(role=m["role"], content=m["content"]) for m in state.history],
                LLMMessage.user(request.message),
            ]

            tools = get_tool_definitions()
            client = LLMClient.from_config()

            async for event in client.stream_complete(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                workflow="chat_stream",
                user_id=user.email,
            ):
                event_type = event.get("type", "")

                if event_type == "response.output_text.delta":
                    text = event.get("delta", "")
                    if text:
                        yield f"data: {{\"type\": \"delta\", \"content\": {repr(text)}}}\n\n"

                elif event_type == "response.output_text.done":
                    text = event.get("text", "")
                    yield f"data: {{\"type\": \"text_done\", \"content\": {repr(text)}}}\n\n"

                elif event_type == "response.function_call_arguments.done":
                    yield f"data: {{\"type\": \"tool_call\", \"name\": \"{event.get('name')}\"}}\n\n"

                elif event_type == "response.completed":
                    yield f"data: {{\"type\": \"done\", \"session_id\": \"{session_id}\"}}\n\n"

        except Exception as e:
            logger.error(f"[Chat] Stream error for {user.email}: {e}")
            yield f"data: {{\"type\": \"error\", \"message\": {repr(str(e))}}}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
        },
    )


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    message: str | None = None,
    session_id: str | None = None,
    user: AuthUser = Depends(require_permission("video:chat:use")),
):
    """
    Upload a file for processing.
    Handles images (design requests) and videos (approval workflow).
    Requires video:chat:use permission.
    """
    session_id = session_id or str(uuid.uuid4())

    logger.info(f"[Chat] File upload from {user.email}: {file.filename}")

    try:
        content = await file.read()
        content_type = file.content_type or ""

        if content_type.startswith("image/"):
            tool_router = ToolRouter()
            image_data = [(content, content_type)]

            response = await main_llm_loop(
                channel_id=session_id,
                user_id=user.id,
                user_input=message or "Please extract the design request details from this image.",
                image_data=image_data,
                channel=None,
                user_name=user.name or user.email,
                user_email=user.email,
                user_companies=user.companies,
                tool_router=tool_router,
            )

            return {
                "success": True,
                "file_id": str(uuid.uuid4()),
                "filename": file.filename,
                "type": "image",
                "response": response,
                "session_id": session_id,
                "timestamp": datetime.now(config.UAE_TZ).isoformat(),
            }

        elif content_type.startswith("video/") or file.filename.lower().endswith(
            (".mp4", ".mov", ".avi", ".mkv", ".webm")
        ):
            return {
                "success": True,
                "file_id": str(uuid.uuid4()),
                "filename": file.filename,
                "type": "video",
                "message": "Video received. Which task number is this for?",
                "session_id": session_id,
            }

        else:
            return {
                "success": False,
                "error": f"Unsupported file type: {content_type}",
            }

    except Exception as e:
        logger.error(f"[Chat] Upload error for {user.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@router.get("/session/{session_id}", response_model=ChatSession)
async def get_session(
    session_id: str,
    user: AuthUser = Depends(require_permission("video:chat:use")),
):
    """Get chat session information."""
    state = get_conversation_state(session_id)

    return ChatSession(
        session_id=session_id,
        created_at=datetime.now(config.UAE_TZ).isoformat(),
        message_count=len(state.history),
    )


@router.delete("/session/{session_id}", response_model=ClearSessionResponse)
async def clear_session(
    session_id: str,
    user: AuthUser = Depends(require_permission("video:chat:use")),
):
    """Clear a chat session and its history."""
    clear_conversation_state(session_id)

    return ClearSessionResponse(
        success=True,
        message=f"Session {session_id} cleared",
    )


@router.get("/sessions")
async def list_sessions(
    user: AuthUser = Depends(require_permission("video:admin:users")),
):
    """
    List active chat sessions.
    Requires video:admin:users permission (admin only).
    """
    from core.llm import _conversation_states

    sessions = []
    for session_id, state in _conversation_states.items():
        sessions.append({
            "session_id": session_id,
            "message_count": len(state.history),
            "has_pending_confirmation": state.pending_confirmation is not None,
            "has_pending_edit": state.pending_edit is not None,
            "has_pending_delete": state.pending_delete is not None,
        })

    return {
        "count": len(sessions),
        "sessions": sessions,
    }


# ============================================================================
# INTERACTIVE ACTIONS (Approval workflow)
# ============================================================================

@router.post("/action", response_model=ActionResponse)
async def handle_action(
    request: ActionRequest,
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """
    Handle interactive actions (button clicks).
    Web equivalent of Slack's interactive payload handling.
    Requires video:review:approve permission.
    """
    logger.info(f"[Chat] Action {request.action_id} for workflow {request.workflow_id} by {user.email}")

    try:
        from core.workflows.approval_flow import ApprovalWorkflow

        workflow = ApprovalWorkflow()
        action_id = request.action_id

        if action_id == "approve_reviewer":
            result = await workflow.handle_reviewer_approve(
                workflow_id=request.workflow_id,
                reviewer_id=user.id,
                reviewer_name=user.name or user.email,
                reviewer_email=user.email,
            )
            return ActionResponse(success=result.success, message=result.message)

        elif action_id == "approve_hos":
            # HoS approval requires higher permission
            if not has_permission(user.permissions, "video:review:final"):
                return ActionResponse(
                    success=False,
                    message="You don't have permission for final approval. Requires video:review:final.",
                )

            result = await workflow.handle_hos_approve(
                workflow_id=request.workflow_id,
                hos_id=user.id,
                hos_name=user.name or user.email,
                hos_email=user.email,
            )
            return ActionResponse(success=result.success, message=result.message)

        elif action_id == "reject_reviewer":
            return ActionResponse(
                success=True,
                message="Please provide rejection details",
                requires_form=True,
                form_type="rejection",
                workflow_id=request.workflow_id,
            )

        elif action_id == "return_hos":
            if not has_permission(user.permissions, "video:review:final"):
                return ActionResponse(
                    success=False,
                    message="You don't have permission to return videos. Requires video:review:final.",
                )

            return ActionResponse(
                success=True,
                message="Please provide return details",
                requires_form=True,
                form_type="return",
                workflow_id=request.workflow_id,
            )

        else:
            return ActionResponse(success=False, message=f"Unknown action: {action_id}")

    except Exception as e:
        logger.error(f"[Chat] Action error for {user.email}: {e}")
        return ActionResponse(success=False, message=f"Error processing action: {str(e)}")


@router.post("/form", response_model=ActionResponse)
async def handle_form_submission(
    request: FormSubmission,
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """
    Handle form submissions (rejection/return modals).
    Web equivalent of Slack's modal view_submission.
    Requires video:review:approve permission.
    """
    logger.info(f"[Chat] Form {request.form_type} for workflow {request.workflow_id} by {user.email}")

    try:
        from core.workflows.approval_flow import ApprovalWorkflow

        workflow = ApprovalWorkflow()

        if request.form_type == "rejection":
            result = await workflow.handle_reviewer_reject(
                workflow_id=request.workflow_id,
                reviewer_id=user.id,
                reviewer_name=user.name or user.email,
                reviewer_email=user.email,
                rejection_reason=request.reason or "",
                rejection_class=request.category or "other",
            )
            return ActionResponse(success=result.success, message=result.message)

        elif request.form_type == "return":
            if not has_permission(user.permissions, "video:review:final"):
                return ActionResponse(
                    success=False,
                    message="You don't have permission to return videos. Requires video:review:final.",
                )

            result = await workflow.handle_hos_return(
                workflow_id=request.workflow_id,
                hos_id=user.id,
                hos_name=user.name or user.email,
                hos_email=user.email,
                return_reason=request.reason or "",
                return_class=request.category or "other",
            )
            return ActionResponse(success=result.success, message=result.message)

        else:
            return ActionResponse(success=False, message=f"Unknown form type: {request.form_type}")

    except Exception as e:
        logger.error(f"[Chat] Form submission error for {user.email}: {e}")
        return ActionResponse(success=False, message=f"Error processing form: {str(e)}")


# ============================================================================
# SLASH COMMAND EQUIVALENTS
# ============================================================================

@router.post("/command")
async def handle_command(
    request: CommandRequest,
    user: AuthUser = Depends(require_permission("video:chat:use")),
):
    """
    Handle slash command equivalents.
    Requires video:chat:use permission.

    Commands:
    - log/design: Start design request flow
    - edit <task_number>: Edit a task
    - delete <task_number>: Delete a task
    - recent: Export recent data
    - help: Show available commands
    """
    session_id = request.session_id or str(uuid.uuid4())
    command = request.command.lower().strip("/")
    args = request.args or ""

    logger.info(f"[Chat] Command /{command} {args} from {user.email}")

    try:
        tool_router = ToolRouter()

        if command in ["log", "design"]:
            user_input = args if args else "I want to log a design request"
            response = await main_llm_loop(
                channel_id=session_id,
                user_id=user.id,
                user_input=user_input,
                image_data=None,
                channel=None,
                user_name=user.name or user.email,
                user_email=user.email,
                user_companies=user.companies,
                tool_router=tool_router,
            )
            return {
                "success": True,
                "command": command,
                "response": response,
                "session_id": session_id,
            }

        elif command == "edit":
            # Edit requires video:tasks:edit permission
            if not has_permission(user.permissions, "video:tasks:edit"):
                return {
                    "success": False,
                    "command": command,
                    "error": "You don't have permission to edit tasks. Requires video:tasks:edit.",
                }

            user_input = f"edit task {args.strip()}" if args and args.strip().isdigit() else (args or "I want to edit a task")
            response = await main_llm_loop(
                channel_id=session_id,
                user_id=user.id,
                user_input=user_input,
                image_data=None,
                channel=None,
                user_name=user.name or user.email,
                user_email=user.email,
                user_companies=user.companies,
                tool_router=tool_router,
            )
            return {
                "success": True,
                "command": command,
                "response": response,
                "session_id": session_id,
            }

        elif command == "delete":
            # Delete requires video:tasks:delete permission
            if not has_permission(user.permissions, "video:tasks:delete"):
                return {
                    "success": False,
                    "command": command,
                    "error": "You don't have permission to delete tasks. Requires video:tasks:delete.",
                }

            if args and args.strip().isdigit():
                user_input = f"delete task {args.strip()}"
                response = await main_llm_loop(
                    channel_id=session_id,
                    user_id=user.id,
                    user_input=user_input,
                    image_data=None,
                    channel=None,
                    user_name=user.name or user.email,
                    user_email=user.email,
                    user_companies=user.companies,
                    tool_router=tool_router,
                )
                return {
                    "success": True,
                    "command": command,
                    "response": response,
                    "session_id": session_id,
                }
            else:
                return {
                    "success": False,
                    "command": command,
                    "error": "Please provide a task number: /delete <task_number>",
                }

        elif command == "recent":
            user_input = "export current data"
            response = await main_llm_loop(
                channel_id=session_id,
                user_id=user.id,
                user_input=user_input,
                image_data=None,
                channel=None,
                user_name=user.name or user.email,
                user_email=user.email,
                user_companies=user.companies,
                tool_router=tool_router,
            )
            return {
                "success": True,
                "command": command,
                "response": response,
                "session_id": session_id,
            }

        elif command == "help":
            help_text = """**Video Critique Commands**

**Design Requests:**
- `/log` or `/design` - Start a new design request
- `/recent` - Export recent task data
- `/edit <task_number>` - Edit an existing task
- `/delete <task_number>` - Delete a task

**Direct Message:**
You can also send messages directly to:
- Paste an email with design request details
- Upload an image/screenshot of a request
- Ask questions about tasks

**Admin Commands:**
Ask me to:
- "list videographers" - See all videographers
- "list locations" - See location mappings
- "add videographer [name] [email]" - Add a new videographer
- "add location [name] to [videographer]" - Map a location"""
            return {
                "success": True,
                "command": command,
                "response": help_text,
                "session_id": session_id,
            }

        else:
            return {
                "success": False,
                "command": command,
                "error": f"Unknown command: /{command}. Use /help for available commands.",
            }

    except Exception as e:
        logger.error(f"[Chat] Command error for {user.email}: {e}")
        return {
            "success": False,
            "command": command,
            "error": str(e),
        }


# ============================================================================
# WORKFLOW STATUS
# ============================================================================

@router.get("/workflows/pending")
async def get_pending_workflows(
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """
    Get pending approval workflows for the current user.
    Requires video:review:approve permission.
    """
    try:
        from db.database import get_database

        db = get_database()

        # Filter workflows by user's email (reviewer or HoS role)
        workflows = await db.get_pending_approvals(reviewer_email=user.email)

        return {
            "count": len(workflows),
            "workflows": [
                {
                    "workflow_id": w.get("id"),
                    "task_number": w.get("task_number"),
                    "folder_name": w.get("folder_name"),
                    "status": w.get("status"),
                    "created_at": w.get("created_at"),
                    "reviewer_approved": w.get("reviewer_approved"),
                    "hos_approved": w.get("hos_approved"),
                }
                for w in workflows
            ],
        }

    except Exception as e:
        logger.error(f"[Chat] Error getting pending workflows for {user.email}: {e}")
        return {"count": 0, "workflows": [], "error": str(e)}


@router.get("/workflows/{workflow_id}")
async def get_workflow_status(
    workflow_id: str,
    user: AuthUser = Depends(require_permission("video:tasks:read")),
):
    """
    Get status of a specific workflow.
    Requires video:tasks:read permission.
    """
    try:
        from db.database import get_database

        db = get_database()
        workflow = await db.get_approval_workflow(workflow_id)

        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        return {
            "workflow_id": workflow.get("id"),
            "task_number": workflow.get("task_number"),
            "folder_name": workflow.get("folder_name"),
            "status": workflow.get("status"),
            "reviewer_id": workflow.get("reviewer_id"),
            "reviewer_approved": workflow.get("reviewer_approved"),
            "hos_id": workflow.get("hos_id"),
            "hos_approved": workflow.get("hos_approved"),
            "created_at": workflow.get("created_at"),
            "updated_at": workflow.get("updated_at"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat] Error getting workflow for {user.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FORM CONFIGURATION (for frontend to build forms)
# ============================================================================

@router.get("/forms/rejection")
async def get_rejection_form_config(
    user: AuthUser = Depends(require_permission("video:review:approve")),
):
    """Get rejection form configuration for frontend."""
    return {
        "title": "Reject Video",
        "submit_text": "Submit",
        "fields": [
            {
                "id": "category",
                "label": "Category",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "technical", "label": "Technical Issue"},
                    {"value": "content", "label": "Content Issue"},
                    {"value": "quality", "label": "Quality Issue"},
                    {"value": "missing", "label": "Missing Elements"},
                    {"value": "other", "label": "Other"},
                ],
            },
            {
                "id": "reason",
                "label": "Details",
                "type": "textarea",
                "required": True,
                "placeholder": "Please describe what needs to be fixed...",
            },
        ],
    }


@router.get("/forms/return")
async def get_return_form_config(
    user: AuthUser = Depends(require_permission("video:review:final")),
):
    """
    Get return form configuration for frontend.
    Requires video:review:final permission (HoS only).
    """
    return {
        "title": "Return for Revision",
        "submit_text": "Submit",
        "fields": [
            {
                "id": "category",
                "label": "Category",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "technical", "label": "Technical Issue"},
                    {"value": "content", "label": "Content Issue"},
                    {"value": "quality", "label": "Quality Issue"},
                    {"value": "missing", "label": "Missing Elements"},
                    {"value": "other", "label": "Other"},
                ],
            },
            {
                "id": "reason",
                "label": "Details",
                "type": "textarea",
                "required": True,
                "placeholder": "Please describe what needs to be revised...",
            },
        ],
    }
