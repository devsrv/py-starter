import hashlib
from src.config import Config
from datetime import datetime, timezone

def get_md5(input_string):
    # Convert string to bytes if it isn't already
    if isinstance(input_string, str):
        input_bytes = input_string.encode('utf-8')
    else:
        input_bytes = input_string
    
    # Create MD5 hash
    md5_hash = hashlib.md5(input_bytes)
    
    # Return hexadecimal representation
    return md5_hash.hexdigest()

def now():
    """Get current datetime in application timezone"""
    return datetime.now(Config.TZ)

def to_app_timezone(dt):
    """Convert datetime to application timezone"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(Config.TZ)