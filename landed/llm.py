"""
landed/llm.py
--------------
One LLM client, two backends. The agent never knows which provider it's
talking to — it speaks one internal format, and this module adapts it.

Internal message format (Anthropic-style blocks, used everywhere in the app):
    {"role": "user"|"assistant", "content": [block, ...]}
blocks:
    {"type": "text", "text": "..."}
    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
    {"type": "tool_result", "tool_use_id": "...", "content": "..."}

chat() returns: {"stop_reason": "tool_use"|"end_turn", "blocks": [...]}

Switch providers in .env:
    LANDED_LLM_PROVIDER=anthropic   (needs ANTHROPIC_API_KEY)
    LANDED_LLM_PROVIDER=bedrock     (needs AWS creds + LANDED_LLM_MODEL)
"""

import os

MAX_TOKENS = 1500


class AnthropicClient:
    def __init__(self, model: str):
        from anthropic import Anthropic
        self.client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = model

    def chat(self, system: str, messages: list, tools: list) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,   # internal format == Anthropic format
            tools=tools,
        )
        blocks = []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id,
                               "name": b.name, "input": b.input})
        return {"stop_reason": resp.stop_reason, "blocks": blocks}


class BedrockClient:
    """Same interface, but speaks AWS Bedrock's `converse` API underneath."""

    def __init__(self, model: str):
        import boto3
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "eu-west-1"),
        )
        self.model = model

    # ---- internal blocks -> converse blocks ----
    @staticmethod
    def _to_converse(messages: list) -> list:
        out = []
        for m in messages:
            content = []
            for b in m["content"]:
                if b["type"] == "text":
                    content.append({"text": b["text"]})
                elif b["type"] == "tool_use":
                    content.append({"toolUse": {
                        "toolUseId": b["id"], "name": b["name"], "input": b["input"]}})
                elif b["type"] == "tool_result":
                    content.append({"toolResult": {
                        "toolUseId": b["tool_use_id"],
                        "content": [{"text": str(b["content"])}]}})
            out.append({"role": m["role"], "content": content})
        return out

    # ---- converse blocks -> internal blocks ----
    @staticmethod
    def _from_converse(content: list) -> list:
        blocks = []
        for b in content:
            if "text" in b:
                blocks.append({"type": "text", "text": b["text"]})
            elif "toolUse" in b:
                tu = b["toolUse"]
                blocks.append({"type": "tool_use", "id": tu["toolUseId"],
                               "name": tu["name"], "input": tu["input"]})
        return blocks

    def chat(self, system: str, messages: list, tools: list) -> dict:
        tool_config = {"tools": [{"toolSpec": {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": {"json": t["input_schema"]},
        }} for t in tools]}

        resp = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=self._to_converse(messages),
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": MAX_TOKENS},
        )
        return {
            "stop_reason": resp["stopReason"],
            "blocks": self._from_converse(resp["output"]["message"]["content"]),
        }


def from_env():
    """Build the right client from .env settings."""
    provider = os.getenv("LANDED_LLM_PROVIDER", "anthropic").strip().lower()
    model = os.getenv("LANDED_LLM_MODEL", "").strip()

    if provider == "anthropic":
        return AnthropicClient(model or "claude-sonnet-4-6")
    if provider == "bedrock":
        if not model:
            raise RuntimeError(
                "Set LANDED_LLM_MODEL in .env to a Claude model id your "
                "Bedrock account can access.")
        return BedrockClient(model)
    raise RuntimeError(f"Unknown LANDED_LLM_PROVIDER: {provider!r} "
                       "(use 'anthropic' or 'bedrock')")
