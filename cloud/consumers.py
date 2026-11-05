import json
from channels.generic.websocket import AsyncWebsocketConsumer

class SmstConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.group_name = f'smst_channel_{self.user.username}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        
    
    async def send_event(self, event):
        await self.send(text_data=json.dumps({
            'type': event['content'],
            'content': event['data']
        }))
        
class SmstAppConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.group_name = f'smst_app_{self.user.username}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        
    
    async def send_event(self, event):
        await self.send(text_data=json.dumps({
            'type': event['content'],
            'content': event['data']
        }))
        
    
    