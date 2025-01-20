"""Feedback UI component."""

import streamlit as st
from core.session import SessionManager


def render_feedback_ui(trace_id: str, session_manager: SessionManager) -> None:
    """Render the feedback UI component."""
    feedback_state = session_manager.get_feedback_state(trace_id)
    if not feedback_state:
        st.write("Was this response helpful?")
        col1, col2, _ = st.columns([1, 1, 8])
        with col1:
            if st.button("👍", key=f"thumbs_up_{trace_id}", help="This response was helpful"):
                session_manager.langfuse.score(
                    trace_id=trace_id,
                    name="user-explicit-feedback",
                    value=1,
                    comment="User found this response helpful",
                )
                session_manager.set_feedback_state(trace_id, "thumbs_up")
                st.rerun()
        with col2:
            if st.button("👎", key=f"thumbs_down_{trace_id}", help="This response was not helpful"):
                session_manager.langfuse.score(
                    trace_id=trace_id,
                    name="user-explicit-feedback",
                    value=0,
                    comment="User did not find this response helpful",
                )
                session_manager.set_feedback_state(trace_id, "thumbs_down")
                st.rerun()
    else:
        if feedback_state == "thumbs_up":
            st.success("Thank you for your feedback! 👍")
        else:
            st.error("Thank you for your feedback! 👎")
