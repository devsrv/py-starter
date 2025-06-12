import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    APP_NAME = os.getenv('APP_NAME', 'My APP')
    APP_MODE = os.getenv('APP_MODE', 'test')
    
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
        },
        'handlers': {
            'default': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
            },
            'file': {
                'level': 'ERROR',
                'formatter': 'standard',
                'class': 'logging.FileHandler',
                'filename': 'audio_processor_errors.log',
                'mode': 'a',
            },
        },
        'loggers': {
            '': {
                'handlers': ['default', 'file'],
                'level': 'INFO',
                'propagate': False
            }
        }
    }
    
    # DigitalOcean Spaces configuration
    DO_SPACES_KEY = os.getenv('DO_SPACES_KEY')
    DO_SPACES_SECRET = os.getenv('DO_SPACES_SECRET')
    DO_SPACES_ENDPOINT = os.getenv('DO_SPACES_ENDPOINT','https://nyc3.digitaloceanspaces.com')
    DO_SPACES_REGION = os.getenv('DO_SPACES_REGION', 'nyc3')
    DO_SPACES_BUCKET = os.getenv('DO_SPACES_BUCKET', 'your-bucket')
    DO_SPACES_BUCKET_OLD = os.getenv('DO_SPACES_BUCKET_OLD', 'your-bucket')
    
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'aw_assessment')
    
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    
    HTTP_SECRET = os.getenv('HTTP_SECRET')
    
    GOOGLE_CHAT_DEV_TEAM_WEBHOOK = os.getenv('GOOGLE_CHAT_DEV_TEAM_WEBHOOK')
    
    # CORS configuration
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '')

    # Concurrency configuration
    MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', 5))
    
    # OpenAI configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
