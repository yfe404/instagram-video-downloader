"""State management for Actor migration and restart handling."""
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from apify import Actor


class ActorState:
    """Manages Actor state for migration and restart handling."""

    STATE_KEY = 'ACTOR_STATE'
    CHECKPOINT_INTERVAL = 10  # Save state every N posts

    def __init__(self):
        """Initialize empty state."""
        self.processed_usernames: List[str] = []
        self.current_username: Optional[str] = None
        self.current_username_index: int = 0
        self.processed_posts: Set[str] = set()
        self.total_videos_downloaded: int = 0
        self.total_errors: int = 0
        self.last_checkpoint: datetime = datetime.utcnow()
        self.posts_since_checkpoint: int = 0

    @classmethod
    async def load(cls) -> 'ActorState':
        """Load state from Apify Key-Value Store.

        Returns:
            ActorState: Loaded state or new empty state if none exists.
        """
        state = cls()

        try:
            saved_state = await Actor.get_value(cls.STATE_KEY)

            if saved_state:
                Actor.log.info('Loading previous Actor state...')
                state.processed_usernames = saved_state.get('processed_usernames', [])
                state.current_username = saved_state.get('current_username')
                state.current_username_index = saved_state.get('current_username_index', 0)
                state.processed_posts = set(saved_state.get('processed_posts', []))
                state.total_videos_downloaded = saved_state.get('total_videos_downloaded', 0)
                state.total_errors = saved_state.get('total_errors', 0)

                Actor.log.info(f'Resumed state: {len(state.processed_usernames)} usernames completed, '
                             f'{len(state.processed_posts)} posts processed, '
                             f'{state.total_videos_downloaded} videos downloaded')
            else:
                Actor.log.info('No previous state found, starting fresh')

        except Exception as e:
            Actor.log.warning(f'Could not load state: {e}. Starting fresh.')

        return state

    async def save(self) -> None:
        """Save current state to Apify Key-Value Store."""
        try:
            state_data = {
                'processed_usernames': self.processed_usernames,
                'current_username': self.current_username,
                'current_username_index': self.current_username_index,
                'processed_posts': list(self.processed_posts),
                'total_videos_downloaded': self.total_videos_downloaded,
                'total_errors': self.total_errors,
                'last_saved': datetime.utcnow().isoformat(),
            }

            await Actor.set_value(self.STATE_KEY, state_data)
            self.last_checkpoint = datetime.utcnow()
            self.posts_since_checkpoint = 0

            Actor.log.debug(f'State saved: {self.total_videos_downloaded} videos, '
                          f'{len(self.processed_posts)} posts processed')

        except Exception as e:
            Actor.log.warning(f'Could not save state: {e}')

    async def checkpoint_if_needed(self) -> None:
        """Save state if checkpoint interval reached."""
        self.posts_since_checkpoint += 1

        if self.posts_since_checkpoint >= self.CHECKPOINT_INTERVAL:
            Actor.log.info(f'Checkpoint: Saving state after {self.posts_since_checkpoint} posts')
            await self.save()

    def is_post_processed(self, post_shortcode: str) -> bool:
        """Check if a post has already been processed.

        Args:
            post_shortcode: Instagram post shortcode.

        Returns:
            True if post already processed, False otherwise.
        """
        return post_shortcode in self.processed_posts

    def mark_post_processed(self, post_shortcode: str) -> None:
        """Mark a post as processed.

        Args:
            post_shortcode: Instagram post shortcode.
        """
        self.processed_posts.add(post_shortcode)

    def is_username_processed(self, username: str) -> bool:
        """Check if a username has already been fully processed.

        Args:
            username: Instagram username.

        Returns:
            True if username already processed, False otherwise.
        """
        return username in self.processed_usernames

    def mark_username_completed(self, username: str) -> None:
        """Mark a username as fully processed.

        Args:
            username: Instagram username.
        """
        if username not in self.processed_usernames:
            self.processed_usernames.append(username)
        self.current_username = None

    def set_current_username(self, username: str, index: int) -> None:
        """Set the username currently being processed.

        Args:
            username: Instagram username.
            index: Index in the usernames list.
        """
        self.current_username = username
        self.current_username_index = index

    def increment_videos_downloaded(self) -> None:
        """Increment the total videos downloaded counter."""
        self.total_videos_downloaded += 1

    def increment_errors(self) -> None:
        """Increment the total errors counter."""
        self.total_errors += 1

    async def clear(self) -> None:
        """Clear saved state from Key-Value Store."""
        try:
            await Actor.set_value(self.STATE_KEY, None)
            Actor.log.info('State cleared')
        except Exception as e:
            Actor.log.warning(f'Could not clear state: {e}')

    def get_resume_info(self) -> Dict[str, Any]:
        """Get information about resume state for logging.

        Returns:
            Dictionary with resume information.
        """
        return {
            'is_resuming': len(self.processed_usernames) > 0 or len(self.processed_posts) > 0,
            'processed_usernames_count': len(self.processed_usernames),
            'processed_posts_count': len(self.processed_posts),
            'current_username': self.current_username,
            'current_index': self.current_username_index,
            'videos_downloaded': self.total_videos_downloaded,
            'errors': self.total_errors,
        }
