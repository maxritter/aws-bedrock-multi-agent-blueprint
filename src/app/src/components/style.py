"""Custom styles for the application."""

import streamlit as st


def apply_custom_style() -> None:
    """Apply custom CSS styles to the application."""
    st.markdown(
        """
        <style>
        [data-testid="stStatusWidget"] {
            visibility: hidden;
            height: 0%;
            position: fixed;
        }
        .file-link {
            text-decoration: none;
            color: #1E88E5;
            cursor: pointer;
        }
        .file-link:hover {
            text-decoration: underline;
        }
        </style>
    """,
        unsafe_allow_html=True,
    )
