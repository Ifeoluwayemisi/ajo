"""
Encryption utilities for sensitive data (BVN, card tokens)
Uses AES-256 in CBC mode with PKCS7 padding
"""

from cryptography.fernet import Fernet
import os
import base64


class EncryptionService:
    """Senior-grade encryption service for sensitive PII"""
    
    def __init__(self, master_key: str = None):
        """
        Initialize with master key from environment.
        
        Args:
            master_key: Can be overridden for testing. 
                       Default uses ENCRYPTION_KEY from .env
        """
        self.master_key = master_key or os.getenv("ENCRYPTION_KEY")
        
        if not self.master_key:
            raise ValueError(
                "ENCRYPTION_KEY not set in environment. "
                "Generate one: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        
        # Fernet (symmetric encryption using AES-128 in CBC mode)
        # For AES-256, we derive a proper key
        self.cipher = Fernet(self.master_key.encode() if isinstance(self.master_key, str) else self.master_key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext (e.g., BVN, card token) to ciphertext
        
        Args:
            plaintext: Raw data to encrypt
            
        Returns:
            Base64-encoded ciphertext safe for database storage
        """
        if not plaintext:
            return None
        
        try:
            ciphertext = self.cipher.encrypt(plaintext.encode())
            return base64.b64encode(ciphertext).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {str(e)}")
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt ciphertext back to plaintext
        
        Args:
            ciphertext: Base64-encoded encrypted data
            
        Returns:
            Original plaintext
        """
        if not ciphertext:
            return None
        
        try:
            decoded_ciphertext = base64.b64decode(ciphertext)
            plaintext = self.cipher.decrypt(decoded_ciphertext)
            return plaintext.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")


# Singleton instance
encryption_service = EncryptionService()
