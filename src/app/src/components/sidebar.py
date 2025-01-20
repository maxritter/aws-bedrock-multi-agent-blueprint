"""Sidebar UI component."""

import time
from typing import List, Tuple

import streamlit as st
from core.s3 import S3Handler
from core.session import SessionManager


def _render_user_info(username: str, session_id: str, session_manager: SessionManager) -> None:
    st.markdown(
        f"""
        **Username**: {username}\n
        **Session ID**: {session_id}
        """
    )
    if st.button("Reset Session", key="reset_session"):
        session_manager.reset()
        st.success("Session reset successfully!")
        time.sleep(2)
        st.rerun()


def _render_file_uploader(session_manager: SessionManager) -> None:
    uploaded_files = st.file_uploader(
        label="**Custom PDF files to be included in your query:**",
        type=["pdf"],
        accept_multiple_files=True,
    )
    session_manager.set_uploaded_files(uploaded_files or [])


def _render_protocol_section(files: List[Tuple[str, str]], s3_handler: S3Handler) -> None:
    st.subheader("Medical Protocols (via RAG):")
    if not files:
        st.info("No files found in RAG bucket")
        return

    for file_key, _ in files:
        display_name = file_key.replace("knowledgeBase/", "", 1)
        download_url = s3_handler.get_download_url(file_key)
        if download_url:
            st.markdown(
                f'<a href="{download_url}" target="_blank" class="file-link">{display_name}</a>',
                unsafe_allow_html=True,
            )
        else:
            st.text(display_name)


def _render_protocol_examples() -> None:
    st.markdown(
        """
        <details>
            <summary>Click to expand sample question</summary>
            <div class="scrollable-content">
                <ol>
                    <li>
                        For protocol 014-01, give me the Overall Design including study phase, primary purpose, indication,
                        population, study type, intervention model, type of control, study blinding, masking and estimated duration.
                    </li>
                    <li>
                        For protocol 014-01, generate me a diagram showing the Maximum Dose Reductions for Selumetinib and MK-8353
                        without, first and second dose reduction for each of the exact different dose numbers in mg that is a separate patient each.
                        Create a separate chart for each drug and use the patient number on the x-axis and the dose reduction on the y-axis, grouped by the reductions.
                    </li>
                    <li>
                        For protocol 014-01, visualize the Dose-finding Rules per mTPI Design for me as a color-coded heatmap
                        with the rule on the colormap, number of participants for DLT at current dose on the x axis and number
                        of participants with at least 1 DLT on the y axis.
                    </li>
                </ol>
            </div>
        </details>
        """,
        unsafe_allow_html=True,
    )


def _render_tool_usage() -> None:
    st.subheader("Tool Usage (via ClinicalTrials.gov):")
    st.markdown(
        """
        **GET /search_trials**
        - Search trials by:
          - Lead sponsor name
          - Disease/condition
          - Overall status (e.g. RECRUITING)
          - Country

        **GET /trial_details**
        - Get detailed trial information by NCT ID
        - Returns phase, status, enrollment, locations, etc.

        **GET /inclusion_criteria**
        - Get inclusion criteria by NCT ID

        **GET /exclusion_criteria**
        - Get exclusion criteria by NCT ID

        **GET /find_closest_trials**
        - Find nearest trial locations by:
          - List of NCT IDs
          - City, State/Province
          - ZIP/Postal code, Country
          - Maximum distance (km)
        """
    )


def _render_tool_examples() -> None:
    st.markdown(
        """
        <details>
            <summary>Click to expand sample question</summary>
            <div class="scrollable-content">
                <ol>
                    <li>
                        Please give me all lung cancer metastatic trials from sponsor Boehringer Ingelheim in the United States that are currently recruiting new patients.
                        For each trial, I want to have all the information available summarized.
                    </li>
                    <li>
                        I want to find the closest lung cancer trial from sponsor Boehringer Ingelheim to my location New York, United States that is currently recruiting.
                        For this closest trial, give me the distance to the study location and the contact details to apply.
                    </li>
                    <li>
                        For the clinical trial NCT05780164, give me the full inclusion and exclusion criteria so I can review them.
                        Present them to me in a table with white background created as an HTML file with a two-column table and no extra text.
                    </li>
                </ol>
            </div>
        </details>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(username: str, session_manager: SessionManager, s3_handler: S3Handler) -> None:
    """Render the sidebar UI component with all its sections.

    Args:
        username: The current user's username
        session_manager: Session management instance
        s3_handler: S3 operations handler
    """
    with st.sidebar:
        _render_user_info(username, session_manager.session_id, session_manager)
        _render_file_uploader(session_manager)

        st.divider()
        _render_protocol_section(s3_handler.list_files(), s3_handler)
        _render_protocol_examples()

        st.divider()
        _render_tool_usage()
        _render_tool_examples()
