from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()

def send_async_msg(username, content, data):
    async_to_sync(channel_layer.group_send)(
        f"smst_channel_{username}",
        {
            'type': 'send.event',
            'content': content,
            'data':data
        }
    )