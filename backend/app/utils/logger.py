"""
Logging configuration module
Provides unified logging to both the console and files
"""

import os
import sys
import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Ensure stdout/stderr use UTF-8 encoding
    Fixes garbled non-ASCII output in Windows consoles
    """
    if sys.platform == 'win32':
        # On Windows, reconfigure standard output as UTF-8
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
# System logs may only contain English/Thai.  Redact all CJK scripts at the
# logging boundary (including third-party OASIS messages), while preserving
# the original value in source/evidence stores.
_HAN_PATTERN = re.compile(
    r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
    r'\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7ff]+'
)


def redact_han_text(value: str) -> str:
    """Redact untrusted CJK text at system-output boundaries."""
    return _HAN_PATTERN.sub('[source text]', str(value))


class LocaleSafeLogFilter(logging.Filter):
    """Keep system logs in the selected UI language without leaking raw CJK errors."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            record.msg = redact_han_text(rendered)
            record.args = ()
        except Exception:
            # Logging must never break the application.
            pass
        return True


def setup_logger(name: str = 'mirofish', level: int = logging.DEBUG) -> logging.Logger:
    """
    Set up a logger
    
    Args:
        name: Logger name
        level: Log level
        
    Returns:
        Configured logger
    """
    # Ensure the log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Create the logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent propagation to the root logger to avoid duplicate output
    logger.propagate = False
    
    # Do not add handlers again if they already exist
    if logger.handlers:
        return logger
    
    # Log formats
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 1. File handler - detailed logs (date-named, rotating)
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    file_handler.addFilter(LocaleSafeLogFilter())
    
    # 2. Console handler - concise logs (INFO and above)
    # Ensure UTF-8 on Windows to avoid garbled non-ASCII text
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    console_handler.addFilter(LocaleSafeLogFilter())
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str = 'mirofish') -> logging.Logger:
    """
    Get a logger (create it if it does not exist)
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Create the default logger
logger = setup_logger()


# Convenience methods
def debug(msg: str, *args, **kwargs) -> None:
    logger.debug(msg, *args, **kwargs)

def info(msg: str, *args, **kwargs) -> None:
    logger.info(msg, *args, **kwargs)

def warning(msg: str, *args, **kwargs) -> None:
    logger.warning(msg, *args, **kwargs)

def error(msg: str, *args, **kwargs) -> None:
    logger.error(msg, *args, **kwargs)

def critical(msg: str, *args, **kwargs) -> None:
    logger.critical(msg, *args, **kwargs)
