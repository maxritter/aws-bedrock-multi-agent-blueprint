"""Main agent class for handling interactions with AWS Bedrock agent."""

import os
from typing import Any, Dict, List, Optional, cast

import boto3
from boto3.session import Session
from core.session import SessionManager
from langfuse import Langfuse
from mypy_boto3_bedrock.client import BedrockClient
from mypy_boto3_bedrock_agent_runtime.client import AgentsforBedrockRuntimeClient
from mypy_boto3_bedrock_agent_runtime.type_defs import (
    InputFileTypeDef,
    ResponseStreamTypeDef,
    SessionStateTypeDef,
)

from .handlers import (
    display_html_files,
    display_images,
    get_html_files,
    get_images,
    handle_citations,
    make_fully_cited_answer,
    process_trace_event,
)
from .types import AgentStats


class Agent:
    """Main agent class for handling interactions with AWS Bedrock agent."""

    def __init__(self, langfuse: Langfuse) -> None:
        """Initialize the agent with AWS Bedrock and Langfuse clients."""
        self.session: Session = boto3.session.Session(region_name=os.getenv("BEDROCK_REGION", "eu-central-1"))
        self.bedrock_agent: BedrockClient = self.session.client("bedrock-agent")
        self.bedrock_agent_runtime: AgentsforBedrockRuntimeClient = self.session.client("bedrock-agent-runtime")
        self.agent_id: str = os.getenv("SUPERVISOR_AGENT_ID")
        self.agent_alias_id: str = os.getenv("SUPERVISOR_AGENT_ALIAS_ID")
        self.langfuse = langfuse

    def _concat_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Concatenate all session messages into a single string."""
        return "\n\n".join(f"role:{m['role']} content:{m['content']}" for m in messages)

    def _get_file_session_state(self, uploaded_files) -> SessionStateTypeDef:
        """Convert uploaded files to session state format."""
        if not uploaded_files:
            return SessionStateTypeDef()

        media_type_map = {
            "pdf": "application/pdf",
            "html": "text/html",
        }

        files: List[InputFileTypeDef] = []
        file_counter = 0
        for file in uploaded_files:
            file_extension = file.name.split(".")[-1].lower()
            if file_extension not in media_type_map:
                continue

            files.append(
                InputFileTypeDef(
                    name=f"input_{file_counter}.{file_extension}",
                    source={
                        "sourceType": "BYTE_CONTENT",
                        "byteContent": {
                            "mediaType": media_type_map[file_extension],
                            "data": file.getvalue(),
                        },
                    },
                    useCase="CHAT",
                )
            )
            file_counter += 1
        return SessionStateTypeDef(files=files)

    def invoke_agent(
        self,
        messages: List[Dict[str, Any]],
        user_id: str,
        session_id: str,
        session_manager: SessionManager,
        uploaded_files=None,
        trace_id: Optional[str] = None,
    ) -> str:
        """Invoke the Bedrock agent with the given messages and context."""
        stats = AgentStats()
        output_text = "Unfortunately, I'm not able to answer that question."
        image_files = []
        html_files = []

        input_text = self._concat_messages(messages)
        session_state = self._get_file_session_state(uploaded_files)

        if not trace_id:
            trace_id = session_manager.create_trace(user_id, messages[-1]["content"])

        langfuse_trace = self.langfuse.trace(
            id=trace_id,
            name="agent-trace",
            user_id=user_id,
            session_id=session_id,
            input=messages[-1]["content"],
        )
        langfuse_span = langfuse_trace.span(
            name="agent-execution",
        )

        response = self.bedrock_agent_runtime.invoke_agent(
            inputText=input_text,
            agentId=self.agent_id,
            agentAliasId=self.agent_alias_id,
            sessionId=session_id,
            enableTrace=True,
            sessionState=session_state,
        )

        for raw_event in response.get("completion", []):
            event = cast(ResponseStreamTypeDef, raw_event)

            if "chunk" in event:
                chunk = event["chunk"]

                if attribution := chunk.get("attribution"):
                    citations = attribution.get("citations", [])
                    handle_citations(citations, langfuse_span)

                if bytes_data := chunk.get("bytes"):
                    output_text = bytes_data.decode("utf-8")
                    output_text = make_fully_cited_answer(output_text, event)

            if "files" in event:
                new_images = get_images(event["files"])
                image_files.extend(new_images)
                new_html = get_html_files(event["files"])
                html_files.extend(new_html)

            if "trace" in event:
                trace = event["trace"]["trace"]
                trace_part = event["trace"]
                process_trace_event(trace, stats, trace_part, langfuse_span)

        processed_images = display_images(image_files)
        processed_html = display_html_files(html_files)

        langfuse_span.generation(
            name="agent-costs",
            model="claude-3-5-sonnet-20240620",
            usage_details={"input": stats.input_tokens, "output": stats.output_tokens},
        )
        langfuse_span.end()

        self.langfuse.trace(id=langfuse_trace.id, output=output_text)
        self.langfuse.flush()

        session_manager.add_assistant_message(output_text, trace_id, processed_images, processed_html)
        return output_text
