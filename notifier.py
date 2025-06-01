#!/usr/bin/env python3
"""
Notifier Module
Handles sending notifications to Discord webhooks.
"""

import json
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("Notifier")


class DiscordNotifier:
    """
    Sends notifications to Discord via webhooks.
    """

    def __init__(self, webhook_url: str = None):
        """
        Initialize the Discord notifier

        Args:
            webhook_url: Discord webhook URL
        """
        self.webhook_url = webhook_url

    def set_webhook(self, webhook_url: str) -> None:
        """
        Update the webhook URL

        Args:
            webhook_url: New Discord webhook URL
        """
        self.webhook_url = webhook_url

    def send_alert(self, title: str, description: str, url: str = "",
                   image: str = "", store: str = "Unknown") -> bool:
        """
        Send an alert to Discord

        Args:
            title: Alert title
            description: Alert description
            url: URL to the product (optional)
            image: URL to product image (optional)
            store: Store name (optional)

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.webhook_url:
            logger.warning("No webhook URL configured, skipping alert")
            return False

        try:
            # Create Discord embed
            embed = {
                "title": title,
                "description": description,
                "color": 5814783,  # Green color
                "timestamp": "",  # This gets filled in by Discord
            }

            # Add URL if provided
            if url:
                embed["url"] = url

            # Add store info to footer
            if store:
                embed["footer"] = {
                    "text": f"Source: {store}"
                }

            # Add image if provided
            if image:
                embed["thumbnail"] = {
                    "url": image
                }

            # Create webhook payload
            payload = {
                "username": "Stock Alert",
                "embeds": [embed]
            }

            # Send the webhook
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            # DEBUG: print the payload being sent
            print("[DEBUG] Webhook Payload:")
            print(json.dumps(payload, indent=2))

            # Send the webhook
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            # Print full response info
            print(f"[DEBUG] Status Code: {response.status_code}")
            print(f"[DEBUG] Response Body: {response.text}")

            if response.status_code in [200, 204]:
                logger.info(f"Successfully sent alert: {title}")
                return True
            else:
                logger.error(f"Failed to send Discord alert. Status: {response.status_code}, Response: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Discord alert: {str(e)}")
            return False

    def send_test_notification(self) -> bool:
        """
        Send a test notification to verify webhook works

        Returns:
            bool: True if sent successfully, False otherwise
        """
        return self.send_alert(
            title="Stock Checker Test Alert",
            description="This is a test alert to verify the Discord webhook is working correctly.",
            store="Test"
        )