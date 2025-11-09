"""Retry utilities with exponential backoff for Instagram scraping."""
import asyncio
import random
from typing import Any, Callable, Tuple, Type
from functools import wraps

from apify import Actor


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 5.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    exceptions_to_retry: Tuple[Type[Exception], ...] = (Exception,)
):
    """Decorator to retry async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_multiplier: Multiplier for exponential backoff
        max_delay: Maximum delay between retries in seconds
        jitter: Add random jitter to prevent thundering herd
        exceptions_to_retry: Tuple of exception types to retry on

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions_to_retry as e:
                    last_exception = e

                    # Don't retry if this was the last attempt
                    if attempt == max_retries:
                        Actor.log.error(
                            f'{func.__name__} failed after {max_retries} retries: {str(e)}'
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        initial_delay * (backoff_multiplier ** attempt),
                        max_delay
                    )

                    # Add jitter if enabled
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    Actor.log.warning(
                        f'{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}. '
                        f'Retrying in {delay:.1f} seconds...'
                    )

                    await asyncio.sleep(delay)

            # Should not reach here, but raise last exception if we do
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def is_retryable_error(exception: Exception) -> bool:
    """Check if an exception is retryable.

    Args:
        exception: Exception to check

    Returns:
        True if the exception is retryable, False otherwise
    """
    import instaloader

    # Retryable Instagram exceptions
    retryable_instagram_errors = (
        instaloader.exceptions.QueryReturnedBadRequestException,  # Challenge required
        instaloader.exceptions.ConnectionException,  # Network issues
        instaloader.exceptions.TooManyRequestsException,  # Rate limiting
    )

    # Check if it's a retryable Instagram error
    if isinstance(exception, retryable_instagram_errors):
        return True

    # Check for specific error messages
    error_msg = str(exception).lower()
    retryable_messages = [
        'challenge_required',
        'challenge',
        'rate limit',
        'too many requests',
        'connection',
        'timeout',
        'temporary',
        '429',
        '503',
    ]

    return any(msg in error_msg for msg in retryable_messages)


def get_error_type(exception: Exception) -> str:
    """Get a user-friendly error type from an exception.

    Args:
        exception: Exception to categorize

    Returns:
        Error type string
    """
    import instaloader

    error_msg = str(exception).lower()

    # Instagram-specific errors
    if isinstance(exception, instaloader.exceptions.ProfileNotExistsException):
        return 'profile_not_found'
    elif isinstance(exception, instaloader.exceptions.PrivateProfileNotFollowedException):
        return 'private_profile'
    elif isinstance(exception, instaloader.exceptions.TwoFactorAuthRequiredException):
        return 'two_factor_required'
    elif isinstance(exception, instaloader.exceptions.BadCredentialsException):
        return 'bad_credentials'
    elif isinstance(exception, instaloader.exceptions.TooManyRequestsException):
        return 'rate_limit'
    elif isinstance(exception, instaloader.exceptions.ConnectionException):
        return 'connection_error'

    # Check error message for specific patterns
    if 'challenge_required' in error_msg or 'challenge' in error_msg:
        return 'challenge_required'
    elif 'rate limit' in error_msg or '429' in error_msg:
        return 'rate_limit'
    elif 'timeout' in error_msg:
        return 'timeout'
    elif 'json' in error_msg and 'decode' in error_msg:
        return 'invalid_response'
    elif '400' in error_msg:
        return 'bad_request'
    elif '401' in error_msg or '403' in error_msg:
        return 'unauthorized'
    elif '404' in error_msg:
        return 'not_found'
    elif '503' in error_msg:
        return 'service_unavailable'

    return 'unknown_error'


def get_user_guidance(error_type: str) -> str:
    """Get user-friendly guidance for an error type.

    Args:
        error_type: Error type from get_error_type()

    Returns:
        Guidance message for the user
    """
    guidance = {
        'challenge_required': 'Instagram requires verification. Try: 1) Use fresh session cookies from browser, 2) Enable proxy, 3) Reduce scraping rate',
        'rate_limit': 'Instagram rate limit detected. Increase delay between profiles or use proxies',
        'profile_not_found': 'Profile does not exist or has been deleted',
        'private_profile': 'Profile is private. Authentication and following required',
        'two_factor_required': 'Two-factor authentication required. Provide TOTP secret',
        'bad_credentials': 'Invalid username or password. Check credentials',
        'connection_error': 'Network connection issue. Check internet connectivity',
        'timeout': 'Request timed out. Try again or increase timeout',
        'invalid_response': 'Instagram returned invalid response. May be temporary',
        'unauthorized': 'Authentication required or session expired. Provide valid credentials or session cookies',
        'service_unavailable': 'Instagram service temporarily unavailable. Try again later',
    }

    return guidance.get(error_type, 'An error occurred. Check logs for details')
