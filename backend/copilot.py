"""GitHub Copilot API client for making LLM requests."""

import os
import httpx
import asyncio
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
from cryptography.fernet import Fernet

# Copilot OAuth Configuration
COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_API_URL = "https://api.githubcopilot.com/chat/completions"

# Copilot Default Headers (mimics VS Code Copilot extension)
COPILOT_EDITOR_VERSION = "vscode/1.104.1"
COPILOT_PLUGIN_VERSION = "copilot-chat/0.26.7"
COPILOT_INTEGRATION_ID = "vscode-chat"
COPILOT_USER_AGENT = "GitHubCopilotChat/0.26.7"

COPILOT_DEFAULT_HEADERS = {
    "Copilot-Integration-Id": COPILOT_INTEGRATION_ID,
    "User-Agent": COPILOT_USER_AGENT,
    "Editor-Version": COPILOT_EDITOR_VERSION,
    "Editor-Plugin-Version": COPILOT_PLUGIN_VERSION,
    "editor-version": COPILOT_EDITOR_VERSION,
    "editor-plugin-version": COPILOT_PLUGIN_VERSION,
    "copilot-vision-request": "true",
}

# Supported Copilot models (base names without provider prefix)
# This is the single source of truth for available Copilot models
_COPILOT_BASE_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o1",
    "o1-mini",
    "o1-pro",
    "o3",
    "o3-mini",
    "o4-mini",
    "claude-sonnet-4",
    "claude-3.5-sonnet",
    "claude-3.7-sonnet",
    "claude-3.7-sonnet-thought",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]

# Fully qualified model names with provider prefix (for API calls)
COPILOT_MODELS = [f"copilot/{model}" for model in _COPILOT_BASE_MODELS]


def get_data_dir() -> Path:
    """Get the data directory for storing tokens."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_encryption_key() -> bytes:
    """Get or create the encryption key for token storage."""
    key_file = get_data_dir() / ".encryption_key"
    if key_file.exists():
        return key_file.read_bytes()
    else:
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        return key


def encrypt_token(token: str) -> str:
    """Encrypt a token for secure storage."""
    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(token.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a stored token."""
    key = get_encryption_key()
    f = Fernet(key)
    decrypted = f.decrypt(base64.b64decode(encrypted_token.encode()))
    return decrypted.decode()


class CopilotService:
    """Service for GitHub Copilot authentication and API calls."""

    def __init__(self):
        self.token_file = get_data_dir() / ".copilot_token"
        self._cached_api_token: Optional[str] = None
        self._api_token_expires: float = 0

    def is_authenticated(self) -> bool:
        """Check if we have a stored GitHub access token."""
        return self.token_file.exists()

    def get_stored_access_token(self) -> Optional[str]:
        """Get the stored GitHub access token."""
        if not self.token_file.exists():
            return None
        try:
            encrypted = self.token_file.read_text()
            return decrypt_token(encrypted)
        except Exception as e:
            print(f"Error reading stored token: {e}")
            return None

    def save_access_token(self, token: str) -> None:
        """Save the GitHub access token securely."""
        encrypted = encrypt_token(token)
        self.token_file.write_text(encrypted)

    def clear_token(self) -> None:
        """Clear the stored token (logout)."""
        if self.token_file.exists():
            self.token_file.unlink()
        self._cached_api_token = None
        self._api_token_expires = 0

    async def get_device_code(self) -> Dict[str, Any]:
        """
        Start the GitHub Device Flow authentication.

        Returns:
            Dict with device_code, user_code, verification_uri, etc.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GITHUB_DEVICE_CODE_URL,
                data={
                    "client_id": COPILOT_CLIENT_ID,
                    "scope": "read:user",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def poll_for_access_token(
        self,
        device_code: str,
        interval: int = 5,
        max_attempts: int = 60
    ) -> Optional[str]:
        """
        Poll GitHub for the access token after user authorizes.

        Args:
            device_code: The device code from get_device_code()
            interval: Polling interval in seconds
            max_attempts: Maximum polling attempts

        Returns:
            The access token if successful, None otherwise
        """
        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                await asyncio.sleep(interval)

                response = await client.post(
                    GITHUB_ACCESS_TOKEN_URL,
                    data={
                        "client_id": COPILOT_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                )

                data = response.json()

                if "access_token" in data:
                    access_token = data["access_token"]
                    self.save_access_token(access_token)
                    return access_token

                error = data.get("error")
                if error == "authorization_pending":
                    continue
                elif error == "slow_down":
                    interval += 5
                    continue
                elif error == "expired_token":
                    return None
                elif error == "access_denied":
                    return None

        return None

    async def get_copilot_api_token(self) -> Optional[str]:
        """
        Get a Copilot API token using the stored GitHub access token.

        The Copilot API token is short-lived and needs to be refreshed.

        Returns:
            The Copilot API token if successful, None otherwise
        """
        import time

        # Check cache first
        if self._cached_api_token and time.time() < self._api_token_expires:
            return self._cached_api_token

        access_token = self.get_stored_access_token()
        if not access_token:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    COPILOT_TOKEN_URL,
                    headers={
                        "Authorization": f"token {access_token}",
                        "Accept": "application/json",
                        **COPILOT_DEFAULT_HEADERS,
                    },
                )
                response.raise_for_status()
                data = response.json()

                self._cached_api_token = data.get("token")
                # Token expires in ~30 minutes, cache for 25 minutes
                self._api_token_expires = time.time() + 25 * 60

                return self._cached_api_token

        except Exception as e:
            print(f"Error getting Copilot API token: {e}")
            return None

    async def query_model(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0
    ) -> Optional[Dict[str, Any]]:
        """
        Query a Copilot model.

        Args:
            model: Copilot model identifier (e.g., "gpt-4o", "claude-sonnet-4")
            messages: List of message dicts with 'role' and 'content'
            timeout: Request timeout in seconds

        Returns:
            Response dict with 'content' and optional 'reasoning_details', or None if failed
        """
        api_token = await self.get_copilot_api_token()
        if not api_token:
            print("Error: No Copilot API token available. Please authenticate first.")
            return None

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            **COPILOT_DEFAULT_HEADERS,
        }

        payload = {
            "model": model,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    COPILOT_API_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()

                data = response.json()
                message = data["choices"][0]["message"]

                return {
                    "content": message.get("content"),
                    "reasoning_details": message.get("reasoning_details"),
                }

        except Exception as e:
            print(f"Error querying Copilot model {model}: {e}")
            return None


# Global singleton instance
copilot_service = CopilotService()


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a Copilot model (convenience function).

    Args:
        model: Copilot model identifier
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict or None if failed
    """
    return await copilot_service.query_model(model, messages, timeout)
