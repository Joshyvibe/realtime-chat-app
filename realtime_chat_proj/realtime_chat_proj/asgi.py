import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Set up Django ASAP
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'realtime_chat_proj.settings')
django.setup()  # Add this line

# Import after Django setup
from chatapp.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns       
        )   
    )
})