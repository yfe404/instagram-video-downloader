"""Entry point for the Instagram Video Downloader Actor."""
import asyncio

from .main import main

if __name__ == '__main__':
    asyncio.run(main())
