from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer, CreateMessageSerializer, UserSerializer, UserListSerializer
from django.db.models import Prefetch

from rest_framework.exceptions import PermissionDenied


class CreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class UserListView(generics.ListAPIView):
    queryset = User.objects.all()  # You can customize this if you need specific user filtering
    serializer_class = UserListSerializer
    permission_classes = [IsAuthenticated]

class ConversationListCreateView(generics.ListCreateAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Simplified query - remove the duplicate prefetch
        return (Conversation.objects
                .filter(participants=self.request.user)
                .prefetch_related('participants'))
    
    def create(self, request, *args, **kwargs):
        participants_data = request.data.get('participants', [])
        
        # Validate that exactly two participants are provided
        if len(participants_data) != 2:
            return Response(
                {'error': 'A conversation must have exactly 2 participants.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Ensure the current user is one of the participants
        if str(request.user.id) not in map(str, participants_data):
            return Response(
                {'error': 'Current user must be a participant.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Fetch user instances
        users = User.objects.filter(id__in=participants_data)
        if users.count() != 2:
            return Response(
                {'error': 'Invalid participants.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if a conversation with these two participants already exists
        existing_conversation = Conversation.objects.filter(
            participants__id=participants_data[0]
        ).filter(
            participants__id=participants_data[1]
        ).distinct()
        
        if existing_conversation.exists():
            return Response(
                {'error': 'A conversation with these participants already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create a new conversation
        conversation = Conversation.objects.create()
        conversation.participants.set(users)
        
        # Serialize and return the new conversation
        serializer = self.get_serializer(conversation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Fetch messages for a specific conversation
        conversation_id = self.kwargs['conversation_id']
        conversation = self.get_conversation(conversation_id)

        return conversation.messages.order_by('timestamp')

    def get_serializer_class(self):
        # Use different serializers for GET and POST
        if self.request.method == 'POST':
            return CreateMessageSerializer
        return MessageSerializer

    def perform_create(self, serializer):
        # Fetch conversation and validate user participation
        print("Incoming data:", self.request.data) 
        conversation_id = self.kwargs['conversation_id']
        conversation = self.get_conversation(conversation_id)

        serializer.save(sender=self.request.user, conversation=conversation)

    def get_conversation(self, conversation_id):
        """Helper method to fetch conversation and check permissions."""
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if self.request.user not in conversation.participants.all():
            raise PermissionDenied("You are not a participant in this conversation.")
        return conversation



class MessageRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self):
        # Only allow access to messages in conversations the user participates in
        conversation_id = self.kwargs['conversation_id']
        return Message.objects.filter(conversation__id=conversation_id)

    def perform_destroy(self, instance):
        # Check if the request user is the sender of the message
        if instance.sender != self.request.user:
            raise PermissionDenied("You can only delete your own messages.")
        instance.delete()
