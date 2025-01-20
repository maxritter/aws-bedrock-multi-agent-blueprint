"""Main application module for the agentic chatbot interface."""

import asyncio
import os
from io import BytesIO
from typing import Optional

import streamlit as st
from agent.agent import Agent
from components.feedback import render_feedback_ui
from components.sidebar import render_sidebar
from components.style import apply_custom_style
from core.auth import Auth
from core.langfuse_client import create_langfuse_client
from core.s3 import S3Handler
from core.session import SessionManager
from streamlit.runtime.scriptrunner import get_script_run_ctx


def display_message_images(images: list) -> None:
    """Display images associated with a message."""
    if not images:
        return

    with st.expander("Generated Images", True):
        for image in images:
            try:
                image_data = BytesIO(image["bytes"])
                st.image(image_data, caption=image.get("name", ""))
            except Exception as e:
                st.error(f"Failed to display image {image.get('name', '')}: {str(e)}")


def display_message_html(html_files: list) -> None:
    """Display HTML files associated with a message."""
    if not html_files:
        return

    with st.expander("Generated HTML", True):
        for html_file in html_files:
            try:
                st.markdown(f"**{html_file.get('name', '')}**")
                # Add wrapper div and script to calculate height
                wrapped_content = f"""
                    <div id="html-wrapper" style="min-height: 250px;">
                        {html_file["content"]}
                    </div>
                    <script>
                        // Wait for the content to load
                        window.addEventListener('load', function() {{
                            // Get the wrapper element
                            var wrapper = document.getElementById('html-wrapper');
                            // Get the actual height of the content
                            var height = Math.max(250, wrapper.scrollHeight);
                            // Set the iframe height through Streamlit
                            window.parent.postMessage({{
                                type: 'streamlit:setFrameHeight',
                                height: height
                            }}, '*');
                        }});
                    </script>
                """
                st.components.v1.html(wrapped_content, scrolling=True, height=250)
            except Exception as e:
                st.error(f"Failed to display HTML {html_file.get('name', '')}: {str(e)}")


async def initialize_session(auth: Optional[Auth] = None) -> str:
    """Initialize the user session and handle authentication."""
    if os.getenv("RUNTIME_ENV") == "local":
        return "Local User"

    if not auth:
        auth = Auth()
    authenticator = auth.get_authenticator()
    is_logged_in = authenticator.login()
    if not is_logged_in:
        st.stop()
    return authenticator.get_username()


async def handle_chat_interaction(
    agent: Agent,
    username: str,
    session_manager: SessionManager,
    prompt: str,
) -> None:
    """Handle a single chat interaction between the user and the agent."""
    session_manager.add_user_message(prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            trace_id = session_manager.create_trace(username, prompt)
            with st.spinner("Agent is thinking.."):
                response = agent.invoke_agent(
                    messages=session_manager.messages,
                    user_id=username,
                    session_id=session_manager.session_id,
                    session_manager=session_manager,
                    uploaded_files=session_manager.uploaded_files,
                    trace_id=trace_id,
                )
            st.write(response)
            display_message_images(session_manager.get_message_images(trace_id))
            display_message_html(session_manager.get_message_html(trace_id))
            render_feedback_ui(trace_id, session_manager)
        except Exception as ex:
            st.error(f"Something went wrong: {str(ex)}")


async def main() -> None:
    """Main application entry point.

    Sets up the Streamlit interface, initializes core services,
    handles authentication, and manages the chat interface.
    """
    st.set_page_config(
        page_title="Bedrock Agent",
        page_icon="🤖",
        menu_items={},
    )

    apply_custom_style()

    if st.get_option("client.toolbarMode") != "minimal":
        st.set_option("client.toolbarMode", "minimal")
        await asyncio.sleep(0.1)
        st.rerun()

    # Initialize core services
    session_manager = SessionManager(
        session_id=get_script_run_ctx().session_id,  # type: ignore
        langfuse=create_langfuse_client(),
    )
    agent = Agent(langfuse=session_manager.langfuse)
    s3_handler = S3Handler()

    # Initialize session and auth
    username = await initialize_session()

    # Render UI components
    render_sidebar(username, session_manager, s3_handler)

    # Display chat history
    for message in session_manager.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                if "trace_id" in message:
                    display_message_images(session_manager.get_message_images(message["trace_id"]))
                    display_message_html(session_manager.get_message_html(message["trace_id"]))
                    render_feedback_ui(message["trace_id"], session_manager)

    # Handle new chat input
    if prompt := st.chat_input("How can I help you today?"):
        await handle_chat_interaction(agent, username, session_manager, prompt)


if __name__ == "__main__":
    asyncio.run(main())
