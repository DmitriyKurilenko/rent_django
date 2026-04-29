"""WebSocket consumer для чата."""
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from boats.chat_helpers import can_access_thread

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Consumer для треда чата.

    URL: /ws/chat/<thread_id>/
    События от клиента:
        {'type': 'message.send', 'body': '...'}
        {'type': 'message.read', 'message_ids': [...]}
    События к клиенту:
        {'type': 'message.new', 'message': {...}}
        {'type': 'message.read_ack', 'message_ids': [...], 'reader_id': N}
        {'type': 'error', 'detail': '...'}
    """

    async def connect(self):
        self.user = self.scope.get('user')
        self.thread_id = int(self.scope['url_route']['kwargs']['thread_id'])
        self.group_name = f'chat_thread_{self.thread_id}'

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        thread = await self._get_thread()
        if thread is None or not await self._can_access(thread):
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get('type')
        if msg_type == 'message.send':
            await self._handle_send(content.get('body', ''))
        elif msg_type == 'message.read':
            await self._handle_read(content.get('message_ids', []))
        else:
            await self.send_json({'type': 'error', 'detail': 'unknown_type'})

    async def _handle_send(self, body: str):
        body = (body or '').strip()
        if not body or len(body) > 5000:
            await self.send_json({'type': 'error', 'detail': 'invalid_body'})
            return

        message = await self._create_message(body)
        if not message:
            await self.send_json({'type': 'error', 'detail': 'create_failed'})
            return

        await self.channel_layer.group_send(self.group_name, {
            'type': 'broadcast.new',
            'message': message,
        })

        try:
            await self._schedule_offline_notify(message['id'])
        except Exception:
            logger.exception('[Chat] Failed to schedule offline notify for message %s', message['id'])

    async def _handle_read(self, message_ids):
        if not isinstance(message_ids, list) or not message_ids:
            return
        ids = await self._mark_read(message_ids)
        if ids:
            await self.channel_layer.group_send(self.group_name, {
                'type': 'broadcast.read',
                'message_ids': ids,
                'reader_id': self.user.pk,
            })

    async def broadcast_new(self, event):
        await self.send_json({'type': 'message.new', 'message': event['message']})

    async def broadcast_read(self, event):
        await self.send_json({
            'type': 'message.read_ack',
            'message_ids': event['message_ids'],
            'reader_id': event['reader_id'],
        })

    @database_sync_to_async
    def _get_thread(self):
        from boats.models import Thread
        try:
            return Thread.objects.get(pk=self.thread_id)
        except Thread.DoesNotExist:
            return None

    @database_sync_to_async
    def _can_access(self, thread):
        return can_access_thread(self.user, thread)

    @database_sync_to_async
    def _create_message(self, body):
        from boats.models import Thread, Message
        from django.db import transaction
        try:
            with transaction.atomic():
                thread = Thread.objects.select_for_update().get(pk=self.thread_id)
                if not can_access_thread(self.user, thread):
                    return None
                msg = Message.objects.create(thread=thread, sender=self.user, body=body)
                thread.last_message_at = msg.created_at
                thread.save(update_fields=['last_message_at', 'updated_at'])
                return {
                    'id': msg.id,
                    'thread_id': self.thread_id,
                    'sender_id': self.user.pk,
                    'sender_name': self.user.get_full_name() or self.user.username,
                    'body': msg.body,
                    'created_at': msg.created_at.isoformat(),
                    'is_system': msg.is_system,
                }
        except Exception:
            logger.exception('[Chat] Failed to create message in thread %s', self.thread_id)
            return None

    @database_sync_to_async
    def _mark_read(self, message_ids):
        from boats.models import Message, MessageRead
        msgs = Message.objects.filter(pk__in=message_ids, thread_id=self.thread_id)
        marked = []
        for msg in msgs:
            _, created = MessageRead.objects.get_or_create(message=msg, user=self.user)
            if created:
                marked.append(msg.pk)
        return marked

    @database_sync_to_async
    def _schedule_offline_notify(self, message_id):
        from boats.tasks import notify_offline_chat_recipients
        notify_offline_chat_recipients.apply_async(args=[message_id], countdown=30)
