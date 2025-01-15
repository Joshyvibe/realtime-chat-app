from rest_framework import serializers
from .models import Conversation, Message
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'password')  # Include additional fields if necessary

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password']
        )
        return user
    
class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']  # Remove email if not needed for chat display


class ConversationSerializer(serializers.ModelSerializer):
    participants = UserListSerializer(many=True, read_only=True)  # Add read_only=True
    
    class Meta:
        model = Conversation
        fields = ['id', 'participants', 'created_at']
    
    def to_representation(self, instance):
        # Additional control over what gets sent to the client
        representation = super().to_representation(instance)
        # You can modify the representation here if needed
        return representation



class MessageSerializer(serializers.ModelSerializer):
    sender = UserListSerializer()
    participants = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'content', 'timestamp', 'participants']

    def get_participants(self, obj):
        # Fetch participants from the related Conversation model
        return UserListSerializer(obj.conversation.participants.all(), many=True).data


class CreateMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['conversation', 'content']
