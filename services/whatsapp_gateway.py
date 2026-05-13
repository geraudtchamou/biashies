"""
WhatsApp Business API Integration Service
Handles sending reports, receipts, and alerts via WhatsApp.
Supports Twilio and Meta Direct APIs.
"""
import os
import requests
import logging
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class WhatsAppMessage:
    to_phone: str  # E.164 format e.g., +234...
    body: str
    media_url: Optional[str] = None
    template_name: Optional[str] = None
    template_params: Optional[List[str]] = None

class WhatsAppGatewayService:
    def __init__(self):
        self.provider = os.getenv('WHATSAPP_PROVIDER', 'meta') # 'meta' or 'twilio'
        self.api_key = os.getenv('WHATSAPP_API_KEY')
        self.phone_number_id = os.getenv('WHATSAPP_PHONE_ID')
        self.base_url = ""
        
        if self.provider == 'meta':
            self.base_url = "https://graph.facebook.com/v17.0"
        elif self.provider == 'twilio':
            self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"
        else:
            raise ValueError("Invalid WhatsApp provider configured")

    def send_text(self, message: WhatsAppMessage) -> bool:
        """Send a simple text message or template."""
        try:
            if self.provider == 'meta':
                return self._send_meta_text(message)
            else:
                return self._send_twilio_text(message)
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {str(e)}")
            return False

    def send_media(self, message: WhatsAppMessage) -> bool:
        """Send a message with an attachment (PDF Receipt/Image Report)."""
        if not message.media_url:
            return self.send_text(message)
        
        try:
            if self.provider == 'meta':
                return self._send_meta_media(message)
            else:
                return self._send_twilio_media(message)
        except Exception as e:
            logger.error(f"Failed to send WhatsApp media: {str(e)}")
            return False

    def _send_meta_text(self, message: WhatsAppMessage) -> bool:
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {"messaging_product": "whatsapp", "to": message.to_phone}
        
        if message.template_name:
            payload["type"] = "template"
            payload["template"] = {
                "name": message.template_name,
                "language": {"code": "en"}, # Dynamic based on user pref
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in (message.template_params or [])]
                    }
                ]
            }
        else:
            payload["type"] = "text"
            payload["text"] = {"body": message.body}

        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.status_code == 200

    def _send_meta_media(self, message: WhatsAppMessage) -> bool:
        # First upload media to Facebook CDN if not already hosted
        media_id = self._upload_media_to_meta(message.media_url)
        
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": message.to_phone,
            "type": "image", # Or document for PDF
            "image": {"id": media_id, "caption": message.body}
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        return response.status_code == 200

    def _upload_media_to_meta(self, file_url: str) -> str:
        """Uploads media to FB CDN and returns Media ID."""
        url = f"{self.base_url}/{self.phone_number_id}/media"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "messaging_product": "whatsapp",
            "type": "document", # Support PDF receipts
            "link": file_url
        }
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()['id']

    def _send_twilio_text(self, message: WhatsAppMessage) -> bool:
        url = f"{self.base_url}/Messages.json"
        auth = (self.account_sid, self.auth_token)
        data = {
            "From": f"whatsapp:+14155238886", # Twilio Sandbox or dedicated number
            "To": f"whatsapp:{message.to_phone}",
            "Body": message.body
        }
        if message.template_name:
            # Twilio Content Builder logic would go here
            pass
            
        resp = requests.post(url, auth=auth, data=data, timeout=10)
        return resp.status_code in [200, 201]

    def _send_twilio_media(self, message: WhatsAppMessage) -> bool:
        url = f"{self.base_url}/Messages.json"
        auth = (self.account_sid, self.auth_token)
        data = {
            "From": f"whatsapp:+14155238886",
            "To": f"whatsapp:{message.to_phone}",
            "Body": message.body,
            "MediaUrl": message.media_url
        }
        resp = requests.post(url, auth=auth, data=data, timeout=15)
        return resp.status_code in [200, 201]

    def handle_webhook(self, payload: dict) -> Optional[str]:
        """
        Process incoming messages/replies from users.
        Returns a response text if auto-reply is needed.
        """
        if self.provider == 'meta':
            # Extract message from Meta webhook structure
            entry = payload.get('entry', [])
            if not entry: return None
            
            changes = entry[0].get('changes', [])
            if not changes: return None
            
            value = changes[0].get('value', {})
            messages = value.get('messages', [])
            
            if messages:
                msg = messages[0]
                user_phone = value.get('contacts', [{}])[0].get('wa_id')
                user_text = msg.get('text', {}).get('body', '')
                
                # Trigger ChatReportService here
                return f"Received: {user_text}. Processing report..."
                
        return None

# Usage Example in Background Worker
# service = WhatsAppGatewayService()
# service.send_text(WhatsAppMessage(to_phone="+2348012345678", body="Your daily profit is ₦50,000"))
