import logging.config
from .config import Config

# Configure logging
logging.config.dictConfig(Config.LOGGING)

# Validate config
Config.validate()