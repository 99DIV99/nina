"""Qwen AI server for NINA MCP chat integration."""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI(title="NINA AI Chat")

MODEL_PATH = os.getenv("MODEL_PATH", "/models")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct")
DEVICE = os.getenv("DEVICE", "cpu")

print(f"Loading model: {MODEL_PATH}/{MODEL_NAME}")
print(f"Device: {DEVICE}")

# Load model and tokenizer
tokenizer = AutoTokenizer.from_pretrained(f"{MODEL_PATH}/{MODEL_NAME}")
model = AutoModelForCausalLM.from_pretrained(
    f"{MODEL_PATH}/{MODEL_NAME}",
    torch_dtype=torch.float16,
    device_map="auto" if DEVICE == "cuda" else {"": "cpu"},
)
print("Model loaded!")


class ChatRequest(BaseModel):
    """Chat request from Django."""
    message: str
    mcp: Optional[dict] = None
    stream: bool = False


class ChatResponse(BaseModel):
    """Chat response."""
    text: str
    model: str
    sources: list = []


@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest) -> ChatResponse:
    """Handle chat completion request.

    TODO: Integrate MCP tools when mcp config is provided.
    For now, this is a simple chat completions endpoint.
    """
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
