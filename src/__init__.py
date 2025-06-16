import logging.config
from .config import Config

# Configure logging
logging.config.dictConfig(Config.LOGGING)

# Suppress noisy third-party loggers
# logging.getLogger('openai').setLevel(logging.WARNING)

# Validate config
Config.validate()