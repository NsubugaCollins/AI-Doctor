"""
WebSocket consumers for real-time consultation updates
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class ConsultationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time consultation updates
    Patients connect to see live agent progress
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.consultation_id = self.scope['url_route']['kwargs']['consultation_id']
        self.room_group_name = f'consultation_{self.consultation_id}'
        
        # Join consultation group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"WebSocket connected for consultation {self.consultation_id}")
        
        # Send initial connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'consultation_id': self.consultation_id,
            'message': 'Connected to consultation updates'
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave consultation group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        logger.info(f"WebSocket disconnected for consultation {self.consultation_id}")
    
    async def receive(self, text_data):
        """Receive message from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Handle ping/pong for keep-alive
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
        except Exception as e:
            logger.error(f"Error receiving WebSocket message: {e}")
    
    async def consultation_update(self, event):
        """
        Receive consultation update from channel layer
        Sent by agents/controller when state changes
        """
        # Send update to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'consultation_update',
            'data': event['data']
        }))
    
    async def agent_started(self, event):
        """Agent started processing"""
        await self.send(text_data=json.dumps({
            'type': 'agent_started',
            'agent': event['agent'],
            'message': event.get('message', f"{event['agent']} started")
        }))
    
    async def agent_progress(self, event):
        """Agent progress update"""
        await self.send(text_data=json.dumps({
            'type': 'agent_progress',
            'agent': event['agent'],
            'message': event.get('message', ''),
            'progress': event.get('progress', 0)
        }))
    
    async def agent_completed(self, event):
        """Agent completed"""
        await self.send(text_data=json.dumps({
            'type': 'agent_completed',
            'agent': event['agent'],
            'message': event.get('message', f"{event['agent']} completed"),
            'data': event.get('data', {})
        }))
    
    async def state_changed(self, event):
        """Consultation state changed"""
        await self.send(text_data=json.dumps({
            'type': 'state_changed',
            'old_state': event.get('old_state'),
            'new_state': event.get('new_state'),
            'message': event.get('message', '')
        }))
