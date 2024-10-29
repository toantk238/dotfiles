import datetime
import logging
import os

# Uncomment the below line to show log of Git cmd from gitPython
# logging.basicConfig(level=logging.INFO)

env_log_level = os.environ.get('LOG_LEVEL', 'WARN').upper()

console_log_level = logging.WARN

if env_log_level == 'WARN':
    console_log_level = logging.WARN
elif env_log_level == 'INFO':
    console_log_level = logging.INFO
elif env_log_level == 'DEBUG':
    console_log_level = logging.DEBUG
elif env_log_level == 'ERROR':
    console_log_level = logging.ERROR


class CustomFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629"""

    grey = '\x1b[38;21m'
    blue = '\x1b[38;5;39m'
    yellow = '\x1b[38;5;226m'
    red = '\x1b[38;5;196m'
    bold_red = '\x1b[31;1m'
    reset = '\x1b[0m'

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# Create custom logger logging all five levels
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Define format for logs
# fmt = '%(asctime)s | %(levelname)8s | %(message)s'
fmt = '%(levelname)8s | %(filename)s:%(lineno)d | %(message)s'

# Create stdout handler for logging to the console (logs all five levels)
stdout_handler = logging.StreamHandler()
stdout_handler.setLevel(console_log_level)
stdout_handler.setFormatter(CustomFormatter(fmt))

# Create file handler for logging to a file (logs all five levels)
today = datetime.date.today()
file_handler = logging.FileHandler('my_app_{}.log'.format(today.strftime('%Y_%m_%d')))
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(fmt))

# Add both handlers to the logger
logger.addHandler(stdout_handler)
logger.addHandler(file_handler)
