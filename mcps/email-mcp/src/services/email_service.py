"""
Email Service for MCP Server.

This service provides email sending functionality using Azure Communication Services.
Supports both plain text and HTML emails with attachments and multiple recipients.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending emails via Azure Communication Services.

    This service handles email composition and delivery through Azure Communication Services.
    It supports both plain text and HTML emails, multiple recipients, CC/BCC, and attachments.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        email_domain: Optional[str] = None,
    ):
        """
        Initialize the Email service.

        Args:
            connection_string: Azure Communication Services connection string
            email_domain: Azure email domain for the sender address
        """
        self.connection_string = connection_string
        self.email_domain = email_domain
        self.email_history: List[Dict] = []
        self.email_count = 0

        if not self.connection_string:
            logger.warning(
                "Azure Communication Services connection string not configured"
            )
        if not self.email_domain:
            logger.warning("Azure email domain not configured")

        # Initialize Azure Email Client
        self.client = None
        if self.connection_string:
            try:
                from azure.communication.email import EmailClient

                self.client = EmailClient.from_connection_string(self.connection_string)
                logger.info(
                    f"EmailService initialized with Azure Communication Services"
                )
                logger.info(f"Email domain: {self.email_domain}")
            except ImportError:
                logger.error(
                    "Azure Communication Email SDK not installed. Install with: pip install azure-communication-email"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Azure Email Client: {str(e)}")
        else:
            logger.warning(
                "EmailService initialized without Azure Communication Services client"
            )

    async def send_email(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> Dict:
        """
        Send an email via Azure Communication Services.

        Args:
            recipient: Email address of the recipient
            subject: Email subject line
            content: Plain text content of the email
            html_content: Optional HTML version of the email content
            cc: Optional list of CC recipients
            bcc: Optional list of BCC recipients
            attachments: Optional list of attachments, each with:
                - name: Filename (e.g., "report.pdf")
                - content_type: MIME type (e.g., "application/pdf")
                - content_base64: Base64-encoded file content

        Returns:
            Dictionary with send status and metadata

        Raises:
            Exception: If email sending fails
        """
        try:
            logger.info(f"Preparing to send email to: {recipient}")

            if not self.client:
                error_msg = "Azure Email Client not initialized. Check connection string configuration."
                logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg,
                    "recipient": recipient,
                    "error": "Client not initialized",
                }

            if not self.email_domain:
                error_msg = "Azure email domain not configured"
                logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg,
                    "recipient": recipient,
                    "error": "Domain not configured",
                }

            # Build the email message
            message = {
                "senderAddress": f"DoNotReply@{self.email_domain}",
                "recipients": {"to": [{"address": recipient}]},
                "content": {"subject": subject, "plainText": content},
            }

            # Add HTML content if provided
            if html_content and html_content.strip():
                message["content"]["html"] = html_content

            # Add CC recipients if provided
            if cc and len(cc) > 0:
                message["recipients"]["cc"] = [{"address": email} for email in cc]

            # Add BCC recipients if provided
            if bcc and len(bcc) > 0:
                message["recipients"]["bcc"] = [{"address": email} for email in bcc]

            # Add attachments if provided
            if attachments:
                valid_attachments = []
                for attachment in attachments:
                    if not isinstance(attachment, dict):
                        logger.warning(f"Skipping invalid attachment: not a dictionary")
                        continue
                    if (
                        "name" not in attachment
                        or "content_type" not in attachment
                        or "content_base64" not in attachment
                    ):
                        logger.warning(
                            f"Skipping invalid attachment: {attachment.get('name', 'unknown')}"
                        )
                        continue

                    valid_attachments.append(
                        {
                            "name": attachment["name"],
                            "contentType": attachment["content_type"],
                            "contentInBase64": attachment["content_base64"],
                        }
                    )

                if valid_attachments:
                    message["attachments"] = valid_attachments
                    logger.info(
                        f"Added {len(valid_attachments)} attachment(s) to email"
                    )

            # Send the email
            logger.info(
                f"Sending email via Azure Communication Services to {recipient}"
            )
            poller = self.client.begin_send(message)
            result = poller.result()

            # Track email in history
            email_record = {
                "recipient": recipient,
                "subject": subject,
                "timestamp": datetime.now().isoformat(),
                "status": "sent",
                "cc": cc,
                "bcc": bcc,
                "message_id": result.get("id", "unknown"),
                "attachment_count": len(attachments) if attachments else 0,
            }
            self.email_history.append(email_record)
            self.email_count += 1

            logger.info(
                f"Email sent successfully to {recipient}. Message ID: {result.get('id')}"
            )

            return {
                "success": True,
                "message": f"Email sent to {recipient}",
                "recipient": recipient,
                "subject": subject,
                "timestamp": email_record["timestamp"],
                "email_count": self.email_count,
                "message_id": result.get("id"),
            }

        except Exception as e:
            logger.error(f"Error sending email: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error sending email: {str(e)}",
                "recipient": recipient,
                "error": str(e),
            }

    async def get_email_history(self, limit: int = 10) -> Dict:
        """
        Get the history of sent emails.

        Args:
            limit: Maximum number of recent emails to return

        Returns:
            Dictionary with email history and statistics
        """
        return {
            "total_emails_sent": self.email_count,
            "recent_emails": self.email_history[-limit:] if self.email_history else [],
            "history_size": len(self.email_history),
        }

    async def test_connection(self) -> Dict:
        """
        Test Azure Communication Services connection and configuration.

        Returns:
            Dictionary with connection test results
        """
        try:
            if not self.client:
                return {
                    "success": False,
                    "message": "Azure Email Client not initialized. Check connection string.",
                    "connection_string_configured": bool(self.connection_string),
                    "domain_configured": bool(self.email_domain),
                }

            if not self.email_domain:
                return {
                    "success": False,
                    "message": "Azure email domain not configured",
                    "connection_string_configured": True,
                    "domain_configured": False,
                }

            logger.info("=" * 70)
            logger.info("📧 Azure Communication Services - Connection Test")
            logger.info("=" * 70)
            logger.info(f"Sender Address: DoNotReply@{self.email_domain}")
            logger.info(
                f"Connection String: {'Configured' if self.connection_string else 'Not configured'}"
            )
            logger.info(
                f"Client Status: {'Initialized' if self.client else 'Not initialized'}"
            )
            logger.info("=" * 70)
            logger.info("✅ Configuration test successful")
            logger.info("=" * 70)

            return {
                "success": True,
                "message": "Azure Communication Services configured successfully",
                "sender_address": f"DoNotReply@{self.email_domain}",
                "email_domain": self.email_domain,
                "client_initialized": True,
            }

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}",
                "error": str(e),
            }


def register_email_tools(mcp, email_service: EmailService):
    """Register email tools with the MCP server."""

    @mcp.tool()
    async def send_email(
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> Dict:
        """
        Send an email using Azure Communication Services.

        This tool allows you to send emails with plain text, optional HTML content,
        and optional file attachments. The email will be sent from the configured
        DoNotReply sender address.

        Args:
            recipient: Email address of the recipient (e.g., "someone@example.com")
            subject: Subject line of the email
            content: Plain text content of the email
            html_content: Optional HTML version of the email content
            attachments: Optional list of attachments. Each attachment should be a dict with:
                - name: Filename (e.g., "report.pdf")
                - content_type: MIME type (e.g., "application/pdf", "text/plain", "image/png")
                - content_base64: Base64-encoded file content

        Returns:
            Dictionary with send status, recipient info, and timestamp

        Example:
            >>> await send_email(
            ...     recipient="colleague@example.com",
            ...     subject="Meeting Reminder",
            ...     content="Don't forget our meeting tomorrow at 10 AM."
            ... )
            {"success": True, "message": "Email sent to colleague@example.com", ...}
        """
        logger.info(
            f"send_email tool called - recipient: {recipient}, subject: {subject}"
        )
        if attachments:
            logger.info(f"Email includes {len(attachments)} attachment(s)")

        result = await email_service.send_email(
            recipient=recipient,
            subject=subject,
            content=content,
            html_content=html_content,
            attachments=attachments,
        )
        return result

    @mcp.tool()
    async def get_email_history(limit: int = 10) -> Dict:
        """
        Get the history of emails sent through this MCP server.

        Shows recently sent emails with recipient, subject, and timestamp information.
        Useful for tracking what emails have been sent.

        Args:
            limit: Maximum number of recent emails to return (default: 10)

        Returns:
            Dictionary with email history and statistics

        Example:
            >>> await get_email_history(5)
            {"total_emails_sent": 42, "recent_emails": [...], "history_size": 42}
        """
        logger.info(f"get_email_history tool called with limit: {limit}")
        history = await email_service.get_email_history(limit)
        return history

    @mcp.tool()
    async def test_email_connection() -> Dict:
        """
        Test the Azure Communication Services email connection and configuration.

        This tool verifies that the email service can connect to Azure Communication Services
        and that all required configuration is in place. Use this to diagnose email
        configuration issues.

        Returns:
            Dictionary with connection test results

        Example:
            >>> await test_email_connection()
            {"success": True, "message": "Azure Communication Services configured successfully", ...}
        """
        logger.info("test_email_connection tool called")
        result = await email_service.test_connection()
        return result

    logger.info("Email tools registered")
