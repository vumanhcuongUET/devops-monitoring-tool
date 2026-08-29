"""
Configuration Security Module

Provides encryption, decryption, sanitization, and secret management
for configuration data.
"""

from typing import Dict, Any, Optional, List
import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class ConfigSecurity:
    """Handle configuration security with encryption."""

    # Fields that should be treated as secrets
    SECRET_FIELDS = [
        "password", "api_key", "secret", "token",
        "credentials", "private_key", "access_key",
        "secret_key", "webhook_url", "auth_token",
        "refresh_token", "client_secret", "passphrase"
    ]

    # Fields that may contain PII
    PII_FIELDS = [
        "email", "phone", "address", "user", "username",
        "contact", "personal", "identity"
    ]

    def __init__(self, encryption_key: Optional[str] = None):
        """Initialize security module.

        Args:
            encryption_key: Optional encryption key (base64 encoded).
                          If None, will use CONFIG_ENCRYPTION_KEY env var.
        """
        self.encryption_key = encryption_key or os.getenv("CONFIG_ENCRYPTION_KEY")
        self.cipher: Optional[Fernet] = None

        if self.encryption_key:
            try:
                # Try to use as Fernet key directly
                self.cipher = Fernet(self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key)
                logger.info("Config encryption enabled")
            except Exception as e:
                logger.warning(f"Invalid encryption key format: {e}")
                self.cipher = None
        else:
            logger.warning("No encryption key provided, secrets will be stored in plain text")

    def sanitize_config(
        self,
        config: Dict[str, Any],
        level: SecurityLevel = SecurityLevel.INTERNAL
    ) -> Dict[str, Any]:
        """Sanitize configuration for logging/display.

        Args:
            config: Configuration to sanitize
            level: Security level for output

        Returns:
            Sanitized configuration
        """
        return self._sanitize_recursive(config, level)

    def _sanitize_recursive(
        self,
        obj: Any,
        level: SecurityLevel
    ) -> Any:
        """Recursively sanitize object."""
        if isinstance(obj, dict):
            sanitized = {}
            for key, value in obj.items():
                if self._is_secret_field(key):
                    sanitized[key] = self._get_redacted_value(level)
                elif self._is_pii_field(key) and level == SecurityLevel.PUBLIC:
                    sanitized[key] = "***REDACTED***"
                else:
                    sanitized[key] = self._sanitize_recursive(value, level)
            return sanitized

        elif isinstance(obj, list):
            return [self._sanitize_recursive(item, level) for item in obj]

        return obj

    def _is_secret_field(self, field_name: str) -> bool:
        """Check if field contains secret data."""
        field_lower = field_name.lower()
        return any(secret in field_lower for secret in self.SECRET_FIELDS)

    def _is_pii_field(self, field_name: str) -> bool:
        """Check if field contains PII data."""
        field_lower = field_name.lower()
        return any(pii in field_lower for pii in self.PII_FIELDS)

    def _get_redacted_value(self, level: SecurityLevel) -> str:
        """Get redacted value based on security level."""
        if level == SecurityLevel.PUBLIC:
            return "***REDACTED***"
        elif level == SecurityLevel.INTERNAL:
            return "***SECRET***"
        elif level == SecurityLevel.CONFIDENTIAL:
            return "***CONFIDENTIAL***"
        else:
            return "***"

    def is_encryption_enabled(self) -> bool:
        """Check if encryption is available."""
        return self.cipher is not None

    async def encrypt_secrets(
        self,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Encrypt secret values in configuration.

        Args:
            config: Configuration to encrypt

        Returns:
            Configuration with encrypted secrets
        """
        if not self.cipher:
            logger.warning("Encryption not available, returning plain config")
            return config

        return await self._encrypt_recursive(config)

    async def _encrypt_recursive(self, obj: Any) -> Any:
        """Recursively encrypt secrets."""
        if isinstance(obj, dict):
            encrypted = {}
            for key, value in obj.items():
                if self._is_secret_field(key) and isinstance(value, str):
                    encrypted[key] = await self._encrypt_value(value)
                else:
                    encrypted[key] = await self._encrypt_recursive(value)
            return encrypted

        elif isinstance(obj, list):
            return [await self._encrypt_recursive(item) for item in obj]

        return obj

    async def _encrypt_value(self, value: str) -> str:
        """Encrypt single value."""
        try:
            encrypted = self.cipher.encrypt(value.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return value

    async def decrypt_secrets(
        self,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Decrypt secret values in configuration.

        Args:
            config: Configuration to decrypt

        Returns:
            Configuration with decrypted secrets
        """
        if not self.cipher:
            return config

        return await self._decrypt_recursive(config)

    async def _decrypt_recursive(self, obj: Any) -> Any:
        """Recursively decrypt secrets."""
        if isinstance(obj, dict):
            decrypted = {}
            for key, value in obj.items():
                if self._is_secret_field(key) and isinstance(value, str):
                    decrypted[key] = await self._decrypt_value(value)
                else:
                    decrypted[key] = await self._decrypt_recursive(value)
            return decrypted

        elif isinstance(obj, list):
            return [await self._decrypt_recursive(item) for item in obj]

        return obj

    async def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt single value."""
        try:
            # Check if value is base64 encoded (encrypted)
            try:
                ciphertext = base64.b64decode(encrypted_value)
                decrypted = self.cipher.decrypt(ciphertext)
                return decrypted.decode()
            except Exception:
                # Not encrypted, return as-is
                return encrypted_value

        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_value

    @staticmethod
    def generate_encryption_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            Base64 encoded encryption key
        """
        return Fernet.generate_key().decode()

    @staticmethod
    def derive_key_from_password(
        password: str,
        salt: Optional[bytes] = None
    ) -> bytes:
        """Derive encryption key from password using PBKDF2.

        Args:
            password: Password to derive key from
            salt: Optional salt (will generate if None)

        Returns:
            Derived key
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def mask_value(self, value: str, visible_chars: int = 4) -> str:
        """Mask a value keeping only first/last characters visible.

        Args:
            value: Value to mask
            visible_chars: Number of characters to keep visible at each end

        Returns:
            Masked value
        """
        if len(value) <= visible_chars * 2:
            return "*" * len(value)

        return (
            value[:visible_chars] +
            "*" * (len(value) - visible_chars * 2) +
            value[-visible_chars:]
        )

    def validate_security_posture(
        self,
        config: Dict[str, Any]
    ) -> List[str]:
        """Validate security posture of configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of security warnings/errors
        """
        issues = []

        def check_recursive(obj: Any, path: str = ""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key

                    # Check for unencrypted secrets
                    if self._is_secret_field(key):
                        if isinstance(value, str) and not value.startswith("***"):
                            if not self._is_encrypted_value(value):
                                issues.append(f"Unencrypted secret at: {current_path}")

                    # Check for plaintext passwords
                    if "password" in key.lower():
                        if isinstance(value, str) and len(value) < 8:
                            issues.append(f"Weak password at: {current_path}")

                    # Check nested
                    check_recursive(value, current_path)

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_recursive(item, f"{path}[{i}]")

        check_recursive(config)
        return issues

    def _is_encrypted_value(self, value: str) -> bool:
        """Check if value appears to be encrypted."""
        try:
            # Try to decode as base64
            decoded = base64.b64decode(value)
            # Check if it looks like Fernet output (has Fernet prefix)
            return decoded.startswith(b"gAAAAA")
        except Exception:
            return False

    def scan_for_secrets(self, config: Dict[str, Any]) -> Dict[str, List[str]]:
        """Scan configuration for potential secret fields.

        Args:
            config: Configuration to scan

        Returns:
            Dictionary with categories of secret fields found
        """
        secrets = {
            "credentials": [],
            "api_keys": [],
            "tokens": [],
            "urls": [],
            "other": []
        }

        def scan_recursive(obj: Any, path: str = ""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key

                    if self._is_secret_field(key):
                        if "password" in key.lower() or "credential" in key.lower():
                            secrets["credentials"].append(current_path)
                        elif "api_key" in key.lower() or "access_key" in key.lower():
                            secrets["api_keys"].append(current_path)
                        elif "token" in key.lower():
                            secrets["tokens"].append(current_path)
                        elif "url" in key.lower() and "webhook" in key.lower():
                            secrets["urls"].append(current_path)
                        else:
                            secrets["other"].append(current_path)

                    scan_recursive(value, current_path)

        scan_recursive(config)

        # Add total count
        total_count = sum(len(v) for v in secrets.values())
        secrets["total_secrets"] = total_count

        return secrets

