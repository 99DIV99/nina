"""Qwen AI server for NINA MCP chat integration."""

import json
import os
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI(title="NINA AI Chat")

MODEL_PATH = os.getenv("MODEL_PATH", "")  # Empty for HuggingFace download
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct")
DEVICE = os.getenv("DEVICE", "cpu")

# Use local path if MODEL_PATH is set and exists, otherwise use HuggingFace repo ID
model_id = f"{MODEL_PATH}/{MODEL_NAME}" if MODEL_PATH and os.path.exists(MODEL_PATH) else MODEL_NAME

print(f"Loading model: {model_id}")
print(f"Device: {DEVICE}")

# Load model and tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_id)
# Use float32 for CPU (float16 not supported on CPU)
dtype = torch.float16 if DEVICE == "cuda" else torch.float32
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=dtype,
    device_map="auto" if DEVICE == "cuda" else {"": "cpu"},
)
print("Model loaded!")


class ChatRequest(BaseModel):
    """Chat request from Django."""
    message: str
    mcp: Optional[Dict[str, Any]] = None
    stream: bool = False
    write_tools: Optional[list] = None  # NEW: list of write tool names


class ChatResponse(BaseModel):
    """Chat response."""
    text: str
    model: str
    sources: list = []
    requires_action: bool = False
    actions: list = []  # NEW: pending actions


def detect_write_intent(response_text: str, write_tools: list) -> Optional[Dict]:
    """Detect if Qwen wants to call a write tool.

    Parse response to see if Qwen is asking to execute a write operation.
    Returns action dict if detected, None otherwise.
    """
    if not write_tools:
        return None

    response_lower = response_text.lower()

    # Check for intent matching write tools
    for tool in write_tools:
        tool_snake = tool.replace(" ", "_").lower()
        if tool_snake in response_lower or tool.lower() in response_lower:
            # Try to extract parameters from response
            # For now, return a placeholder - user will need to confirm
            return {
                "tool": tool,
                "intent": response_text[:200],  # First 200 chars as description
            }

    return None


@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest) -> ChatResponse:
    """Handle chat completion request.

    Checks for write tool intent and returns pending action if detected.
    """
    write_tools = request.write_tools or []

    # Build system prompt with write tool instructions
    if write_tools:
        system_prompt = f"""You are NINA AI, a helpful business assistant.

IMPORTANT - When you need to use a WRITE TOOL ({', '.join(write_tools)}):
1. Respond with this exact JSON format (nothing else):
{{"tool": "tool_name", "params": {{...}}, "description": "what you will do"}}

For example: {{"tool": "create_customer", "params": {{"name": "John", "phone": "555-1234"}}, "description": "Add customer John (555-1234)"}}

For READ tools, answer normally in plain text.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ]
    else:
        messages = [{"role": "user", "content": request.message}]

    # Apply chat template
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    # Tokenize
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    # Generate response
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
        )

    # Decode only the new tokens
    response = tokenizer.decode(
        outputs[0][inputs['input_ids'].shape[1]:],
        skip_special_tokens=True
    )

    # Try to parse as JSON (tool call)
    if write_tools:
        try:
            # Try parsing response as JSON
            parsed = json.loads(response.strip())

            if isinstance(parsed, dict) and "tool" in parsed:
                # Qwen wants to call a tool
                tool_name = parsed.get("tool")

                if tool_name in write_tools:
                    # This is a write tool - create pending action
                    mcp_config = request.mcp or {}
                    pending_endpoint = mcp_config.get("pending_endpoint", "http://localhost:8000/api/v1/mcp/pending/")

                    import httpx

                    try:
                        # Call Django to create pending action
                        action_response = httpx.post(
                            pending_endpoint,
                            json={
                                "tool_name": tool_name,
                                "tool_params": parsed.get("params", {}),
                                "description": parsed.get("description", f"Execute {tool_name}"),
                            },
                            headers={"X-MCP-Token": mcp_config.get("token", "")},
                            timeout=10
                        )
                        action_response.raise_for_status()
                        action = action_response.json()

                        return ChatResponse(
                            text=f"I'll {action.get('description', tool_name)}. Please confirm.",
                            model=MODEL_NAME,
                            sources=[],
                            requires_action=True,
                            actions=[{
                                "id": action.get("action_id"),
                                "type": tool_name,
                                "description": action.get("description", ""),
                                "params": parsed.get("params", {}),
                            }]
                        )
                    except Exception as e:
                        # Failed to create pending action, return error
                        return ChatResponse(
                            text=f"Would you like me to {tool_name}? Please confirm.",
                            model=MODEL_NAME,
                            requires_action=True,
                            actions=[{
                                "id": "pending",  # Placeholder
                                "type": tool_name,
                                "description": parsed.get("description", f"Execute {tool_name}"),
                                "params": parsed.get("params", {}),
                            }]
                        )
                else:
                    # Read tool or unknown tool - call directly
                    # For now, return text response
                    return ChatResponse(
                        text=response,
                        model=MODEL_NAME,
                    )
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON, normal text response
            pass

    return ChatResponse(
        text=response,
        model=MODEL_NAME,
        sources=[],
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model": MODEL_NAME,
        "device": DEVICE,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
