"""Langfuse client initialization."""

import os

from langfuse import Langfuse


def create_langfuse_client() -> Langfuse:
    """Create and initialize a Langfuse client."""
    return Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host="https://cloud.langfuse.com",
    )
