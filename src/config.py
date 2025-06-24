from src.filesystem.providers import StorageProvider
from src.filesystem.file_manager import StorageProvider
from src.logging.daily_file_handler import DailyFileHandler
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from pathlib import Path

load_dotenv()

class Config:
    APP_NAME = os.getenv('APP_NAME', 'My APP')
    APP_MODE = os.getenv('APP_MODE', 'development')
    APP_DEBUG = os.getenv('APP_DEBUG', 'True').lower() in ('true', '1', 'yes')
    DEBUG = APP_MODE != 'production' and APP_DEBUG
    
    TZ = ZoneInfo(os.getenv('TZ', 'America/New_York'))
    
    LOG_DIR = Path('storage/logs')
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_LEVEL = 'DEBUG' if DEBUG else 'INFO'
    
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'detailed': {
                'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
        },
        'handlers': {
            'console': {
                'level': LOG_LEVEL,
                'formatter': 'detailed' if DEBUG else 'standard',
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout'
            },
            'file_daily': {
                '()': DailyFileHandler,
                'filename_pattern': str(LOG_DIR / 'app-{date}.log'),
                'level': 'INFO',
                'formatter': 'standard',
                'encoding': 'utf-8',
            },
            'error_daily': {
                '()': DailyFileHandler,
                'filename_pattern': str(LOG_DIR / 'error-{date}.log'),
                'level': 'ERROR',
                'formatter': 'detailed',
                'encoding': 'utf-8',
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console', 'file_daily', 'error_daily'],
                'level': 'DEBUG' if DEBUG else 'INFO', # Only debug YOUR app in debug mode
                'propagate': False
            },
            'fastapi': {
                'handlers': ['console', 'file_daily'],
                'level': 'INFO',
                'propagate': False
            }
        }
    }
    
    DEFAULT_FILESYSTEM = os.getenv('DEFAULT_FILESYSTEM', 'local').lower()
    
    DO_SPACES_KEY = os.getenv('DO_SPACES_KEY', '')
    DO_SPACES_SECRET = os.getenv('DO_SPACES_SECRET', '')
    DO_SPACES_REGION = os.getenv('DO_SPACES_REGION', 'nyc3')
    DO_SPACES_BUCKET = os.getenv('DO_SPACES_BUCKET', 'your-bucket')
    DO_SPACES_BUCKET_OLD = os.getenv('DO_SPACES_BUCKET_OLD', 'your-bucket')
    
    MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'your-bucket')
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://localhost:9000')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', '')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', '')
    
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    AWS_REGION_NAME = os.getenv('AWS_REGION_NAME', 'us-east-1')
    AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME', '')
    
    LOCAL_STORAGE_FULL_PATH = './storage/app/' + os.getenv('LOCAL_STORAGE_PATH', 'media')
    
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'aw_assessment')
    
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
    MYSQL_USER = os.getenv('MYSQL_USER', 'root')
    MYSQL_DB = os.getenv('MYSQL_DB', 'test')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    
    HTTP_SECRET = os.getenv('HTTP_SECRET')
    
    GOOGLE_CHAT_DEV_TEAM_WEBHOOK: str = os.getenv('GOOGLE_CHAT_DEV_TEAM_WEBHOOK', '')
    
    # CORS configuration
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '')

    # Concurrency configuration
    MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', 5))
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []
        
        storage_providers = {storage.value for storage in StorageProvider}
        
        if cls.DEFAULT_FILESYSTEM not in storage_providers:
            errors.append(f"Invalid DEFAULT_FILESYSTEM: {cls.DEFAULT_FILESYSTEM}. Must be one of {storage_providers}")
        
        if cls.APP_MODE == 'production':
            if not cls.HTTP_SECRET:
                errors.append("HTTP_SECRET is required in production")
            if not cls.ALLOWED_ORIGINS:
                errors.append("ALLOWED_ORIGINS is required in production")
                
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
    @classmethod
    def get_absolute_path(cls, relative_path: str) -> Path:
        # Get the project root (assuming this function is in a file within the project)
        project_root = Path(__file__).parent.parent  # Adjust based on your file location
        return project_root / relative_path
