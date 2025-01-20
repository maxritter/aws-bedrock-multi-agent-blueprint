"""Session management for the application."""

import uuid
from typing import Any, Dict, List, Optional

import streamlit as st
from langfuse import Langfuse


class SessionManager:
    """Manages session state and interactions."""

    def __init__(self, session_id: str, langfuse: Langfuse) -> None:
        """Initialize the session manager."""
        self.langfuse = langfuse

        # Initialize session state if needed
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "feedback_states" not in st.session_state:
            st.session_state.feedback_states = {}
        if "uploaded_files" not in st.session_state:
            st.session_state.uploaded_files = []
        if "message_images" not in st.session_state:
            st.session_state.message_images = {}
        if "message_html" not in st.session_state:
            st.session_state.message_html = {}
        if "session_id" not in st.session_state:
            st.session_state.session_id = session_id

    @property
    def session_id(self) -> str:
        """Get the current session ID."""
        return st.session_state.session_id

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get the chat messages."""
        return st.session_state.messages

    @property
    def uploaded_files(self) -> List[Any]:
        """Get the uploaded files."""
        return st.session_state.uploaded_files

    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat history."""
        st.session_state.messages.append({"role": "user", "content": content})

    def add_assistant_message(
        self,
        content: str,
        trace_id: str,
        images: Optional[List[Dict[str, Any]]] = None,
        html_files: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add an assistant message to the chat history."""
        st.session_state.messages.append({"role": "assistant", "content": content, "trace_id": trace_id})
        if images:
            st.session_state.message_images[trace_id] = images
        if html_files:
            st.session_state.message_html[trace_id] = html_files

    def get_message_images(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get images associated with a message."""
        return st.session_state.message_images.get(trace_id, [])

    def get_message_html(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get HTML files associated with a message."""
        return st.session_state.message_html.get(trace_id, [])

    def create_trace(self, user_id: str, input_text: str) -> str:
        """Create a new trace for the current interaction."""
        return self.langfuse.trace(
            name="agent-trace",
            user_id=user_id,
            session_id=self.session_id,
            input=input_text,
        ).id

    def set_uploaded_files(self, files: List[Any]) -> None:
        """Set the uploaded files for the current session."""
        st.session_state.uploaded_files = files

    def get_feedback_state(self, trace_id: str) -> Optional[str]:
        """Get the feedback state for a trace."""
        return st.session_state.feedback_states.get(trace_id)

    def set_feedback_state(self, trace_id: str, state: str) -> None:
        """Set the feedback state for a trace."""
        st.session_state.feedback_states[trace_id] = state

    def reset(self) -> None:
        """Reset all session state variables."""
        st.session_state.messages = []
        st.session_state.feedback_states = {}
        st.session_state.uploaded_files = []
        st.session_state.message_images = {}
        st.session_state.message_html = {}
        st.session_state.session_id = str(uuid.uuid4())
