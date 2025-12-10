"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio

from . import storage
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings
from .copilot import copilot_service, COPILOT_MODELS
from .providers import provider_registry
from .config import COUNCIL_MODELS, COPILOT_MODELS as CONFIG_COPILOT_MODELS, OPENROUTER_MODELS

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


class CopilotDeviceCodeResponse(BaseModel):
    """Response from Copilot device code request."""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class CopilotPollRequest(BaseModel):
    """Request to poll for Copilot access token."""
    device_code: str


class CopilotStatusResponse(BaseModel):
    """Response with Copilot authentication status."""
    authenticated: bool
    available_models: List[str]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


# ==================== Copilot Authentication Endpoints ====================

@app.get("/api/copilot/status", response_model=CopilotStatusResponse)
async def copilot_status():
    """Check Copilot authentication status."""
    authenticated = copilot_service.is_authenticated()
    return {
        "authenticated": authenticated,
        "available_models": COPILOT_MODELS if authenticated else []
    }


@app.post("/api/copilot/auth", response_model=CopilotDeviceCodeResponse)
async def copilot_auth():
    """
    Start Copilot OAuth device flow.
    Returns device_code and user_code for user to authorize.
    """
    try:
        result = await copilot_service.get_device_code()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start auth flow: {str(e)}")


@app.post("/api/copilot/token")
async def copilot_poll_token(request: CopilotPollRequest):
    """
    Poll for Copilot access token after user authorizes.
    This endpoint will wait until the user authorizes or timeout.
    """
    try:
        access_token = await copilot_service.poll_for_access_token(
            request.device_code,
            interval=5,
            max_attempts=24  # 2 minutes max
        )
        if access_token:
            return {"success": True, "message": "Authentication successful"}
        else:
            return {"success": False, "message": "Authentication failed or expired"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get token: {str(e)}")


@app.post("/api/copilot/logout")
async def copilot_logout():
    """Clear Copilot authentication."""
    copilot_service.clear_token()
    return {"success": True, "message": "Logged out successfully"}


# ==================== Provider & Model Endpoints ====================

@app.get("/api/providers")
async def list_providers():
    """List all available providers and their status."""
    providers = []
    for name in provider_registry.list_providers():
        provider = provider_registry.get(name)
        if provider:
            providers.append({
                "name": name,
                "available": provider.is_available(),
                "models": provider.supported_models if provider.is_available() else []
            })
    return providers


@app.get("/api/models")
async def list_models():
    """List all available models across all providers."""
    models = []
    for name in provider_registry.list_available_providers():
        provider = provider_registry.get(name)
        if provider:
            for model in provider.supported_models:
                models.append({
                    "id": f"{name}/{model}" if name != "openrouter" else model,
                    "provider": name,
                    "name": model
                })
    return models


@app.get("/api/council/config")
async def get_council_config():
    """Get current council configuration."""
    return {
        "council_models": COUNCIL_MODELS,
        "copilot_models": CONFIG_COPILOT_MODELS,
        "openrouter_models": OPENROUTER_MODELS,
    }


# ==================== Conversation Endpoints ====================


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
