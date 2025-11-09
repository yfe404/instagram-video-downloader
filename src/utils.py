"""Utility functions for Instagram Video Downloader Actor."""
import re
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional
from http.cookiejar import Cookie

from apify import Actor


def parse_date_filter(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string in YYYY-MM-DD format to datetime object."""
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        Actor.log.warning(f'Invalid date format: {date_str}. Expected YYYY-MM-DD')
        return None


def should_include_post(
    post,
    filter_options: Dict[str, Any],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> bool:
    """Check if post should be included based on filters."""
    # Check if videos only
    if filter_options.get('videosOnly', True) and not post.is_video:
        return False

    # Check minimum likes
    min_likes = filter_options.get('minLikes', 0)
    if min_likes > 0 and post.likes < min_likes:
        return False

    # Check date range
    if date_from and post.date_utc < date_from:
        return False

    if date_to and post.date_utc > date_to:
        return False

    return True


def extract_hashtags(caption: str) -> List[str]:
    """Extract hashtags from caption text."""
    if not caption:
        return []

    # Find all hashtags (words starting with #)
    hashtags = re.findall(r'#(\w+)', caption)
    return hashtags


def extract_comments(post) -> List[Dict[str, Any]]:
    """Extract comments from a post."""
    comments = []

    try:
        # Limit to first 100 comments to avoid rate limiting
        for comment in list(post.get_comments())[:100]:
            comments.append({
                'owner': comment.owner.username if hasattr(comment, 'owner') else 'unknown',
                'text': comment.text,
                'created_at': comment.created_at_utc.isoformat() if hasattr(comment, 'created_at_utc') else None,
                'likes': comment.likes_count if hasattr(comment, 'likes_count') else 0,
            })
    except Exception as e:
        Actor.log.warning(f'Error extracting comments: {e}')

    return comments


async def download_video_to_kv_store(post, proxy_url: Optional[str] = None) -> str:
    """Download video file and store it in Apify Key-Value Store."""
    if not post.is_video:
        raise ValueError('Post does not contain a video')

    video_url = post.video_url
    if not video_url:
        raise ValueError('Video URL not found')

    Actor.log.info(f'Downloading video from: {video_url}')

    # Download video content
    proxies = None
    if proxy_url:
        proxies = {
            'http': proxy_url,
            'https': proxy_url,
        }

    response = requests.get(video_url, stream=True, timeout=60, proxies=proxies)
    response.raise_for_status()

    # Generate storage key
    storage_key = f'video_{post.shortcode}.mp4'

    # Save to Key-Value Store
    await Actor.set_value(storage_key, response.content, content_type='video/mp4')

    return storage_key


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to remove invalid characters."""
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def parse_netscape_cookies(cookie_content: str) -> Dict[str, str]:
    """Parse Netscape HTTP Cookie File format to dictionary.

    Format:
    # Netscape HTTP Cookie File
    domain  flag  path  secure  expiration  name  value

    Example:
    .instagram.com  TRUE  /  TRUE  0  sessionid  123456789
    """
    cookies = {}

    for line in cookie_content.strip().split('\n'):
        # Skip comments and empty lines
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Split by tab or multiple spaces
        parts = re.split(r'\t+|\s{2,}', line)

        # Netscape format: domain, flag, path, secure, expiration, name, value
        if len(parts) >= 7:
            name = parts[5]
            value = parts[6]
            cookies[name] = value
        elif len(parts) == 2:
            # Also support simple "name value" format
            cookies[parts[0]] = parts[1]

    return cookies
