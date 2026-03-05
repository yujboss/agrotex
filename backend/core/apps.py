from django.apps import AppConfig
from django.conf import settings
import os


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        # Ensure media directory exists
        media_root = settings.MEDIA_ROOT
        if not os.path.exists(media_root):
            os.makedirs(media_root, exist_ok=True)
        # Ensure trucks subdirectory exists
        trucks_dir = os.path.join(media_root, 'trucks')
        if not os.path.exists(trucks_dir):
            os.makedirs(trucks_dir, exist_ok=True)
