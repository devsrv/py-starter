import hashlib
from src.config import Config
from datetime import datetime, timezone


def get_md5(input_string: str | bytes) -> str:
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


def utcnow():
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def to_app_timezone(dt: datetime) -> datetime:
    """Convert datetime to application timezone"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(Config.TZ)
    
    
def _optional_bool(value: str|None, default: bool) -> bool:
    """Read an optional boolean var"""
    
    _TRUE = {"1", "true", "yes", "on", "y", "t"}
    _FALSE = {"0", "false", "no", "off", "n", "f"}

    if value is None or value.strip() == "":
        return default
    val = value.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    print(
        f"FATAL: {value!r} is not a boolean. "
        f"Use one of {sorted(_TRUE)} or {sorted(_FALSE)}.",
        file=sys.stderr,
    )
    sys.exit(1)