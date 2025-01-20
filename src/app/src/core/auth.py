"""Authentication module for handling Cognito user authentication."""

import os

from streamlit_cognito_auth import CognitoAuthenticator


class Auth:
    """Authentication handler for AWS Cognito integration."""

    def __init__(self) -> None:
        """Initialize the authentication handler with Cognito configuration."""
        authenticator = CognitoAuthenticator(
            pool_id=os.getenv("USER_POOL_ID"),
            app_client_id=os.getenv("USER_POOL_CLIENT_ID"),
            app_client_secret=os.getenv("USER_POOL_CLIENT_SECRET"),
        )
        self.authenticator = authenticator

    def get_authenticator(self) -> CognitoAuthenticator:
        """Get the configured Cognito authenticator instance."""
        return self.authenticator
