from asgiref.sync import sync_to_async
import json
import jwt
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.conf import settings
from .models import Conversation, Message
from urllib.parse import parse_qs

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get the token from the query string
        query_string = self.scope['query_string'].decode('utf-8')  # Decode bytes to string
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]  # Retrieve token value

        if token:
            try:
                # Validate the token
                decoded_data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                self.user = await self.get_user(decoded_data['user_id'])  # Get the user from the token
                self.scope["user"] = self.user  # Attach the user to the scope
                
            except jwt.ExpiredSignatureError:
                await self.close(code=4000)  # Close the connection if token has expired
                return
            except jwt.InvalidTokenError:
                await self.close(code=4001)  # Close the connection for invalid token
                return
        else:
            await self.close(code=4002)  # Close connection if no token is provided
            return

        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f"chat_{self.conversation_id}"

        # Add this channel to the group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Accept the WebSocket connection
        await self.accept()

        user_data = await self.get_user_data(self.user)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "online_status",
                "online_users": [user_data],  # Notify of new online user
                "status": "online",
            }
        )



    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            # Notify others about offline status
            user_data = await self.get_user_data(self.scope["user"])
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "online_status",
                    "online_users": [user_data],  # Notify of user going offline
                    "status": "offline",
                }
            )

            # Remove this channel from the group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )


    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        event_type = text_data_json.get('type')

        if event_type == 'chat_message':
            message_content = text_data_json.get('message')
            user_id = text_data_json.get('user')

            try:
                user = await self.get_user(user_id)
                conversation = await self.get_conversation(self.conversation_id)

                from .serializers import UserListSerializer
                user_data = UserListSerializer(user).data

                # Save the message to the database
                message = await self.save_message(conversation, user, message_content)

                # Broadcast the message to the group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message.content,
                        'user': user_data,
                        'timestamp': message.timestamp.isoformat()
                    }
                )
            except Exception as e:
                print(f"Error saving message: {e}")

        elif event_type == 'typing':
            try:
                user_data = await self.get_user_data(self.scope["user"])
                receiver_id = text_data_json.get('receiver')  # This should now be just the ID
                
                # Add proper type checking
                if receiver_id is not None:
                    # Convert receiver_id to int only if it's a string or number
                    if isinstance(receiver_id, (str, int, float)):
                        receiver_id = int(receiver_id)
                        
                        if receiver_id != self.scope["user"].id:
                            print(f"{user_data['username']} is typing for receiver: {receiver_id}")

                            # Notify the group
                            await self.channel_layer.group_send(
                                self.room_group_name,
                                {
                                    'type': 'typing',
                                    'user': user_data,
                                    'receiver': receiver_id,
                                }
                            )
                        else:
                            print(f"Receiver is same as sender: {receiver_id}")
                    else:
                        print(f"Invalid receiver_id type: {type(receiver_id)}")
                else:
                    print("No receiver_id provided")
                    
            except ValueError as e:
                print(f"Error converting receiver_id to int: {e}")
            except Exception as e:
                print(f"Error processing typing event: {e}")

    async def chat_message(self, event):
        message = event['message']
        user = event['user']
        timestamp = event['timestamp']
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message,
            'user': user,
            'timestamp': timestamp
        }))

    async def typing(self, event):
        user = event['user']
        receiver = event.get('receiver')
        is_typing = event.get('is_typing', False)
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user': user,
            'receiver': receiver,
            'is_typing': is_typing
        }))


    async def online_status(self, event):
        # Broadcast the online/offline status to the WebSocket
        await self.send(text_data=json.dumps(event))


    @sync_to_async
    def get_user(self, user_id):
        return User.objects.get(id=user_id)

    @sync_to_async
    def get_user_data(self, user):
        from .serializers import UserListSerializer
        return UserListSerializer(user).data

    @sync_to_async
    def get_conversation(self, conversation_id):
        try:
            return Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            print(f"Conversation with ID {conversation_id} does not exist.")
            return None

        

    @sync_to_async
    def save_message(self, conversation, user, content):
        return Message.objects.create(
            conversation=conversation,
            sender=user,
            content=content
        )
