"""Main module for Instagram Video Downloader Actor."""
import os
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import instaloader
from apify import Actor
from apify_shared.consts import ActorEventTypes

from .utils import (
    download_video_to_kv_store,
    extract_comments,
    extract_hashtags,
    parse_date_filter,
    parse_netscape_cookies,
    should_include_post,
)
from .state import ActorState
from .retry_utils import (
    retry_with_backoff,
    is_retryable_error,
    get_error_type,
    get_user_guidance,
)


async def main() -> None:
    """Main Actor entry point."""
    async with Actor:
        # Load state for migration/restart handling
        state = await ActorState.load()

        # Setup migration event handler
        async def handle_migration():
            """Handle Actor migration event."""
            Actor.log.info('Migration event received, saving state...')
            await state.save()
            Actor.log.info('State saved successfully for migration')

        # Register migration handler
        Actor.on(ActorEventTypes.MIGRATING, handle_migration)

        # Log resume information if resuming
        resume_info = state.get_resume_info()
        if resume_info['is_resuming']:
            Actor.log.info(f'Resuming from previous run:')
            Actor.log.info(f'  - Processed usernames: {resume_info["processed_usernames_count"]}')
            Actor.log.info(f'  - Processed posts: {resume_info["processed_posts_count"]}')
            Actor.log.info(f'  - Videos downloaded: {resume_info["videos_downloaded"]}')
            Actor.log.info(f'  - Errors: {resume_info["errors"]}')
            if resume_info['current_username']:
                Actor.log.info(f'  - Resuming at username: {resume_info["current_username"]}')

        # Get Actor input
        actor_input = await Actor.get_input() or {}
        Actor.log.info(f'Actor input: {actor_input}')

        # Parse input parameters
        usernames: List[str] = actor_input.get('usernames', [])
        content_types: List[str] = actor_input.get('contentTypes', ['posts', 'reels'])
        max_videos: int = actor_input.get('maxVideosPerProfile', 50)
        storage_method: str = actor_input.get('storageMethod', 'both')
        include_metadata: Dict[str, bool] = actor_input.get('includeMetadata', {
            'basicInfo': True,
            'engagementMetrics': True,
            'comments': False,
            'locationHashtags': True,
        })
        filter_options: Dict[str, Any] = actor_input.get('filterOptions', {
            'videosOnly': True,
            'minLikes': 0,
        })
        proxy_config_input = actor_input.get('proxyConfiguration')
        session_cookies_input = actor_input.get('sessionCookies')

        # Retry configuration
        max_retries: int = actor_input.get('maxRetries', 3)
        retry_delay: float = actor_input.get('retryDelay', 5.0)
        delay_between_profiles: float = actor_input.get('delayBetweenProfiles', 2.0)

        # Validate input
        if not usernames:
            Actor.log.error('No usernames provided!')
            await Actor.fail(status_message='No usernames provided in input')
            return

        Actor.log.info(f'Starting Instagram video download for {len(usernames)} profile(s)')

        # Create proxy configuration if provided
        proxy_configuration = None
        if proxy_config_input:
            proxy_configuration = await Actor.create_proxy_configuration(
                actor_proxy_input=proxy_config_input
            )
            Actor.log.info('Proxy configuration initialized')

        # Initialize Instaloader (no authentication for public content)
        loader = instaloader.Instaloader(
            quiet=False,
            download_video_thumbnails=False,
            download_geotags=include_metadata.get('locationHashtags', False),
            download_comments=include_metadata.get('comments', False),
            save_metadata=False,
            compress_json=False,
        )

        # Configure proxy if available
        if proxy_configuration:
            proxy_url = await proxy_configuration.new_url()
            if proxy_url:
                loader.context._session.proxies = {
                    'http': proxy_url,
                    'https': proxy_url,
                }
                Actor.log.info(f'Using proxy: {proxy_url}')

        # Login to Instagram if session cookies provided
        logged_in = False

        if session_cookies_input:
            Actor.log.info('Session cookies provided in input, attempting to use them...')
            try:
                # Parse Netscape cookie format to dictionary
                session_cookies = parse_netscape_cookies(session_cookies_input)

                if not session_cookies:
                    raise ValueError('No valid cookies found in the provided cookie file')

                Actor.log.info(f'Parsed {len(session_cookies)} cookies from Netscape format')

                # Update loader's session cookies
                loader.context._session.cookies.update(session_cookies)

                # Test if the session is valid
                username = loader.test_login()
                if username:
                    Actor.log.info(f'Successfully logged in as {username} using provided session cookies')
                    logged_in = True
                else:
                    Actor.log.warning('Provided session cookies are invalid or expired')
            except Exception as e:
                Actor.log.error(f'Failed to parse or use session cookies: {e}')
                raise ValueError(f'Invalid session cookies format. Expected Netscape HTTP Cookie File format. Error: {str(e)}')
        else:
            Actor.log.warning('No Instagram session cookies provided - you may encounter 401/403 errors due to Instagram\'s anti-scraping measures')

        # Parse date filters if provided
        date_from = parse_date_filter(filter_options.get('dateFrom'))
        date_to = parse_date_filter(filter_options.get('dateTo'))

        # Create retry wrapper for profile loading
        @retry_with_backoff(
            max_retries=max_retries,
            initial_delay=retry_delay,
            exceptions_to_retry=(
                instaloader.exceptions.QueryReturnedBadRequestException,
                instaloader.exceptions.ConnectionException,
                instaloader.exceptions.TooManyRequestsException,
            )
        )
        async def load_profile_with_retry(username: str):
            """Load Instagram profile with retry logic."""
            return instaloader.Profile.from_username(loader.context, username)

        # Process each username (resume from saved index if needed)
        start_index = state.current_username_index if resume_info['is_resuming'] else 0

        for index, username in enumerate(usernames[start_index:], start=start_index):
            # Skip if already completed
            if state.is_username_processed(username):
                Actor.log.info(f'Skipping already processed username: {username}')
                continue

            # Add delay between profiles to avoid rate limiting
            if index > start_index and delay_between_profiles > 0:
                Actor.log.info(f'Waiting {delay_between_profiles}s before next profile...')
                await asyncio.sleep(delay_between_profiles)

            # Set current username in state
            state.set_current_username(username, index)
            await state.save()  # Save immediately when starting new username

            Actor.log.info(f'Processing profile: {username} ({index + 1}/{len(usernames)})')

            try:
                # Load profile with retry logic
                profile = await load_profile_with_retry(username)
                Actor.log.info(f'Loaded profile: {username} (Posts: {profile.mediacount})')

                videos_count = 0

                # Process posts
                if 'posts' in content_types:
                    Actor.log.info(f'Downloading posts from {username}...')
                    async for result in process_posts(
                        loader, profile, profile.get_posts(),
                        'post', max_videos, videos_count, storage_method,
                        include_metadata, filter_options, date_from, date_to,
                        proxy_configuration, state
                    ):
                        if result:
                            await Actor.push_data(result)
                            videos_count += 1
                            state.increment_videos_downloaded()
                            await state.checkpoint_if_needed()

                # Process reels
                if 'reels' in content_types and videos_count < max_videos:
                    Actor.log.info(f'Downloading reels from {username}...')
                    try:
                        async for result in process_posts(
                            loader, profile, profile.get_reels(),
                            'reel', max_videos, videos_count, storage_method,
                            include_metadata, filter_options, date_from, date_to,
                            proxy_configuration, state
                        ):
                            if result:
                                await Actor.push_data(result)
                                videos_count += 1
                                state.increment_videos_downloaded()
                                await state.checkpoint_if_needed()
                    except Exception as e:
                        Actor.log.warning(f'Could not fetch reels for {username}: {e}')

                # Process IGTV
                if 'igtv' in content_types and videos_count < max_videos:
                    Actor.log.info(f'Downloading IGTV from {username}...')
                    try:
                        async for result in process_posts(
                            loader, profile, profile.get_igtv_posts(),
                            'igtv', max_videos, videos_count, storage_method,
                            include_metadata, filter_options, date_from, date_to,
                            proxy_configuration, state
                        ):
                            if result:
                                await Actor.push_data(result)
                                videos_count += 1
                                state.increment_videos_downloaded()
                                await state.checkpoint_if_needed()
                    except Exception as e:
                        Actor.log.warning(f'Could not fetch IGTV for {username}: {e}')

                # Process stories (Note: Stories require authentication, will skip for public scraping)
                if 'stories' in content_types and videos_count < max_videos:
                    Actor.log.warning(f'Stories require authentication - skipping for {username}')

                Actor.log.info(f'Completed {username}: {videos_count} videos downloaded')

                # Mark username as completed and save state
                state.mark_username_completed(username)
                await state.save()

            except instaloader.exceptions.ProfileNotExistsException:
                Actor.log.error(f'Profile not found: {username}')
                state.increment_errors()
                await Actor.push_data({
                    'username': username,
                    'post_url': None,
                    'is_video': False,
                    'content_type': 'error',
                    'download_status': 'failed',
                    'error_message': 'Profile not found',
                    'scraped_at': datetime.utcnow().isoformat(),
                })
                # Mark as completed even on error to avoid retry loops
                state.mark_username_completed(username)
                await state.save()
            except instaloader.exceptions.PrivateProfileNotFollowedException:
                Actor.log.error(f'Profile is private: {username}')
                state.increment_errors()
                await Actor.push_data({
                    'username': username,
                    'post_url': None,
                    'is_video': False,
                    'content_type': 'error',
                    'download_status': 'failed',
                    'error_message': 'Private profile - authentication required',
                    'scraped_at': datetime.utcnow().isoformat(),
                })
                # Mark as completed even on error to avoid retry loops
                state.mark_username_completed(username)
                await state.save()
            except Exception as e:
                Actor.log.exception(f'Error processing profile {username}: {e}')
                state.increment_errors()

                # Classify the error
                error_type = get_error_type(e)
                is_retryable = is_retryable_error(e)
                guidance = get_user_guidance(error_type)

                # Log user guidance for retryable errors
                if is_retryable:
                    Actor.log.warning(f'Retryable error detected: {error_type}')
                    Actor.log.info(f'Guidance: {guidance}')

                await Actor.push_data({
                    'username': username,
                    'post_url': None,
                    'is_video': False,
                    'content_type': 'error',
                    'download_status': 'failed',
                    'error_message': str(e),
                    'error_type': error_type,
                    'is_retryable': is_retryable,
                    'user_guidance': guidance,
                    'scraped_at': datetime.utcnow().isoformat(),
                })

                # Only mark as completed if error is not retryable
                # This allows retrying retryable errors in future runs
                if not is_retryable:
                    state.mark_username_completed(username)
                    Actor.log.info(f'Marked {username} as completed (non-retryable error)')
                else:
                    Actor.log.warning(f'Not marking {username} as completed (retryable error - can retry in next run)')

                await state.save()

        # Final statistics
        Actor.log.info(f'Scraping completed!')
        Actor.log.info(f'Total videos downloaded: {state.total_videos_downloaded}')
        Actor.log.info(f'Total errors: {state.total_errors}')

        # Clear state after successful completion
        await state.clear()


async def process_posts(
    loader: instaloader.Instaloader,
    profile: instaloader.Profile,
    posts_iterator,
    content_type: str,
    max_videos: int,
    current_count: int,
    storage_method: str,
    include_metadata: Dict[str, bool],
    filter_options: Dict[str, Any],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    proxy_configuration=None,
    state: Optional[ActorState] = None,
):
    """Process posts from an iterator and yield video data."""
    for post in posts_iterator:
        # Check if we've reached the limit
        if max_videos > 0 and current_count >= max_videos:
            break

        # Deduplication: Skip if post already processed
        if state and state.is_post_processed(post.shortcode):
            Actor.log.debug(f'Skipping already processed post: {post.shortcode}')
            continue

        # Apply filters
        if not should_include_post(post, filter_options, date_from, date_to):
            continue

        try:
            # Extract video data
            video_data = await extract_video_data(
                loader, post, content_type, storage_method, include_metadata, proxy_configuration
            )

            if video_data:
                # Mark post as processed
                if state:
                    state.mark_post_processed(post.shortcode)

                yield video_data
                current_count += 1

        except Exception as e:
            Actor.log.warning(f'Error processing post {post.shortcode}: {e}')

            # Mark post as processed even on error to avoid retry loops
            if state:
                state.mark_post_processed(post.shortcode)

            yield {
                'username': post.owner_username,
                'post_shortcode': post.shortcode,
                'post_url': f'https://www.instagram.com/p/{post.shortcode}/',
                'is_video': post.is_video,
                'content_type': content_type,
                'download_status': 'failed',
                'error_message': str(e),
                'scraped_at': datetime.utcnow().isoformat(),
            }


async def extract_video_data(
    loader: instaloader.Instaloader,
    post,
    content_type: str,
    storage_method: str,
    include_metadata: Dict[str, bool],
    proxy_configuration=None,
) -> Optional[Dict[str, Any]]:
    """Extract video data from a post."""
    # Skip if not a video (when videos_only filter is enabled)
    if not post.is_video:
        return None

    Actor.log.info(f'Processing video: {post.shortcode}')

    video_data = {
        'username': post.owner_username,
        'post_shortcode': post.shortcode,
        'post_url': f'https://www.instagram.com/p/{post.shortcode}/',
        'is_video': post.is_video,
        'content_type': content_type,
        'scraped_at': datetime.utcnow().isoformat(),
    }

    # Basic info
    if include_metadata.get('basicInfo', True):
        video_data.update({
            'caption': post.caption if post.caption else '',
            'timestamp': post.date_utc.isoformat() if post.date_utc else None,
            'owner': post.owner_username,
            'likes': post.likes,
        })

    # Engagement metrics
    if include_metadata.get('engagementMetrics', True):
        video_data.update({
            'comments_count': post.comments,
            'video_views': post.video_view_count if hasattr(post, 'video_view_count') else None,
            'video_duration': post.video_duration if hasattr(post, 'video_duration') else None,
        })

        # Calculate engagement rate
        if hasattr(post, 'owner_profile'):
            followers = post.owner_profile.followers if post.owner_profile else 1
        else:
            followers = 1
        engagement = ((post.likes + post.comments) / max(followers, 1)) * 100
        video_data['engagement_rate'] = round(engagement, 2)

    # Location and hashtags
    if include_metadata.get('locationHashtags', True):
        video_data['hashtags'] = extract_hashtags(post.caption) if post.caption else []
        video_data['location'] = post.location.name if post.location else None

    # Comments
    if include_metadata.get('comments', False):
        try:
            video_data['comments'] = extract_comments(post)
        except Exception as e:
            Actor.log.warning(f'Could not extract comments for {post.shortcode}: {e}')
            video_data['comments'] = []

    # Video URL (always include for dataset_urls or both methods)
    if storage_method in ['dataset_urls', 'both']:
        video_data['video_url'] = post.video_url if post.is_video else None

    # Download to Key-Value Store
    if storage_method in ['key_value_store', 'both']:
        try:
            # Get proxy URL if proxy configuration is available
            proxy_url = None
            if proxy_configuration:
                proxy_url = await proxy_configuration.new_url()

            storage_key = await download_video_to_kv_store(post, proxy_url)
            video_data['video_storage_key'] = storage_key
            video_data['download_status'] = 'success'
            Actor.log.info(f'Video downloaded to KV store: {storage_key}')
        except Exception as e:
            Actor.log.error(f'Failed to download video to KV store: {e}')
            video_data['download_status'] = 'failed'
            video_data['error_message'] = f'KV store download failed: {str(e)}'
    else:
        video_data['download_status'] = 'success'

    return video_data
