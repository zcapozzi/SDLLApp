"""Configurable logging utilities"""

import logging
from datetime import datetime
from functools import wraps
from flask import current_app, request


class SDLLLogger:
    """Custom logger with configurable levels per feature"""

    OFF = 'OFF'
    ON = 'ON'
    EXTREME = 'EXTREME'

    def __init__(self, feature_name):
        self.feature_name = feature_name
        self.logger = logging.getLogger(f'sdll.{feature_name}')

    def _get_level(self):
        """Get logging level for this feature from config"""
        config = getattr(current_app, 'logging_config', {})
        return config.get(self.feature_name, config.get('default', 'ON'))

    def _should_log(self, required_level):
        """Check if we should log at this level"""
        level = self._get_level()
        if level == self.OFF:
            return False
        if level == self.ON and required_level == self.EXTREME:
            return False
        return True

    def info(self, message, **kwargs):
        """Log at ON level"""
        if self._should_log(self.ON):
            timestamp = datetime.now().isoformat()
            self.logger.info(f'[{timestamp}] {message}', extra=kwargs)

    def detail(self, message, **kwargs):
        """Log at EXTREME level (detailed steps)"""
        if self._should_log(self.EXTREME):
            timestamp = datetime.now().isoformat()
            self.logger.debug(f'[{timestamp}] [DETAIL] {message}', extra=kwargs)

    def request_start(self, action):
        """Log the start of a request"""
        if self._should_log(self.ON):
            timestamp = datetime.now().isoformat()
            user = getattr(request, 'user', 'anonymous')
            self.logger.info(f'[{timestamp}] START: {action} by {user}')

    def request_end(self, action, success=True):
        """Log the end of a request"""
        if self._should_log(self.ON):
            timestamp = datetime.now().isoformat()
            status = 'SUCCESS' if success else 'FAILED'
            self.logger.info(f'[{timestamp}] END: {action} - {status}')


def logged_action(feature_name, action_name):
    """Decorator to automatically log actions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            logger = SDLLLogger(feature_name)
            logger.request_start(action_name)
            try:
                result = f(*args, **kwargs)
                logger.request_end(action_name, success=True)
                return result
            except Exception as e:
                logger.request_end(action_name, success=False)
                logger.info(f'Error in {action_name}: {str(e)}')
                raise
        return decorated_function
    return decorator
