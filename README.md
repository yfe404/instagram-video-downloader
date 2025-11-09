# Instagram Video Downloader Actor

Download videos from Instagram profiles, reels, stories, and IGTV using Instaloader. This Actor extracts comprehensive metadata including engagement metrics, comments, hashtags, and location data.

## Features

- Download videos from multiple Instagram profiles
- Support for multiple content types:
  - Profile posts (feed)
  - Reels
  - Stories (requires authentication - currently not supported)
  - IGTV videos
- Flexible storage options:
  - Store video URLs in dataset
  - Download videos to Key-Value Store
  - Both methods simultaneously
- Comprehensive metadata extraction:
  - Basic info (caption, date, owner, likes)
  - Engagement metrics (comments count, video views, engagement rate)
  - Comments (optional, up to 100 per post)
  - Location and hashtags
- Advanced filtering:
  - Videos only filter
  - Minimum likes threshold
  - Date range filtering
  - Maximum videos per profile limit

## Input Parameters

### Required

- **Instagram Usernames** (array of strings)
  - List of Instagram usernames to download videos from
  - Do not include the @ symbol
  - Example: `["natgeo", "nasa"]`

### Optional

- **Instagram Session Cookies (Netscape Format)** (string)
  - Provide your Instagram session cookies in Netscape HTTP Cookie File format
  - Export cookies from your browser using extensions like 'Get cookies.txt' or 'EditThisCookie'
  - See **Authentication** section below for details on obtaining session cookies
  - Without authentication, you may encounter 401/403 errors due to Instagram's anti-scraping measures

- **Content Types to Download** (array)
  - Select which types of video content to download
  - Options: `posts`, `reels`, `stories`, `igtv`
  - Default: `["posts", "reels"]`

- **Max Videos Per Profile** (integer)
  - Maximum number of videos to download per profile
  - Set to 0 for unlimited
  - Default: `50`
  - Range: 0-1000

- **Storage Method** (string)
  - How to store downloaded videos
  - Options:
    - `dataset_urls`: Save video URLs and metadata to dataset
    - `key_value_store`: Download videos to KV store
    - `both`: Videos in KV store + URLs in dataset
  - Default: `both`

- **Metadata to Include** (object)
  - `basicInfo` (boolean): Caption, date, owner username, likes count
  - `engagementMetrics` (boolean): Comments count, video views, engagement rate
  - `comments` (boolean): Download all comments on the video posts
  - `locationHashtags` (boolean): Geotags and hashtags used in the post

- **Filter Options** (object)
  - `videosOnly` (boolean): Skip posts that don't contain videos (default: true)
  - `minLikes` (integer): Only download videos with at least this many likes
  - `dateFrom` (string): Only download videos from this date onwards (YYYY-MM-DD)
  - `dateTo` (string): Only download videos up to this date (YYYY-MM-DD)

- **Max Retries** (integer)
  - Maximum number of retry attempts for failed requests (rate limits, challenges, etc.)
  - Default: `3`
  - Range: 0-10

- **Initial Retry Delay** (number)
  - Initial delay in seconds before first retry (doubles with each subsequent retry)
  - Default: `5`
  - Range: 1-60

- **Delay Between Profiles** (number)
  - Seconds to wait between processing profiles to avoid rate limiting
  - Default: `2`
  - Range: 0-60

## Output

The Actor stores data in the Apify Dataset. Each item contains:

```json
{
  "username": "example_user",
  "post_shortcode": "ABC123DEF",
  "post_url": "https://www.instagram.com/p/ABC123DEF/",
  "video_url": "https://instagram.com/...",
  "video_storage_key": "video_ABC123DEF.mp4",
  "is_video": true,
  "content_type": "post",
  "caption": "Amazing video caption here",
  "timestamp": "2025-11-05T10:30:00",
  "owner": "example_user",
  "likes": 1234,
  "comments_count": 56,
  "video_views": 5678,
  "video_duration": 30.5,
  "engagement_rate": 2.45,
  "hashtags": ["tag1", "tag2"],
  "location": "City, Country",
  "comments": [
    {
      "owner": "commenter_username",
      "text": "Great video!",
      "created_at": "2025-11-05T11:00:00",
      "likes": 10
    }
  ],
  "download_status": "success",
  "scraped_at": "2025-11-05T12:00:00"
}
```

## Example Usage

### Basic Usage - Download Videos from Single Profile

```json
{
  "usernames": ["natgeo"],
  "contentTypes": ["posts", "reels"],
  "maxVideosPerProfile": 20
}
```

### Advanced Usage - Multiple Profiles with Filters

```json
{
  "usernames": ["natgeo", "nasa", "bbcearth"],
  "contentTypes": ["posts", "reels", "igtv"],
  "maxVideosPerProfile": 50,
  "storageMethod": "both",
  "includeMetadata": {
    "basicInfo": true,
    "engagementMetrics": true,
    "comments": true,
    "locationHashtags": true
  },
  "filterOptions": {
    "videosOnly": true,
    "minLikes": 1000,
    "dateFrom": "2024-01-01",
    "dateTo": "2025-12-31"
  }
}
```

### Download Only Video URLs (No File Downloads)

```json
{
  "usernames": ["example_user"],
  "contentTypes": ["posts"],
  "maxVideosPerProfile": 10,
  "storageMethod": "dataset_urls"
}
```

### Using Session Cookies for Authentication

```json
{
  "usernames": ["private_account"],
  "sessionCookies": "# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tyour_session_id\n.instagram.com\tTRUE\t/\tTRUE\t0\tcsrftoken\tyour_csrf_token",
  "contentTypes": ["posts", "reels"],
  "maxVideosPerProfile": 30,
  "storageMethod": "both"
}
```

## Authentication

### Session Cookies

Use your existing Instagram session cookies to authenticate without providing your password.

**How to export cookies:**

1. **Using Chrome/Edge with "Get cookies.txt LOCALLY" extension:**
   - Install [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Log in to Instagram in your browser
   - Click the extension icon and click "Export" for instagram.com
   - Copy the entire content and paste it into the "Session Cookies" field

2. **Using Firefox with "cookies.txt" extension:**
   - Install [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
   - Log in to Instagram
   - Click the extension and export cookies for instagram.com
   - Copy and paste into the "Session Cookies" field

3. **Using any browser Developer Tools:**
   - Log in to Instagram
   - Open Developer Tools (F12)
   - Go to Application/Storage → Cookies → https://www.instagram.com
   - Find `sessionid` and `csrftoken` cookies
   - Format manually as Netscape format (see example below)

**Netscape Cookie Format Example:**
```
# Netscape HTTP Cookie File
.instagram.com	TRUE	/	TRUE	0	sessionid	your_session_id_here
.instagram.com	TRUE	/	TRUE	0	csrftoken	your_csrf_token_here
```

**Advantages:**
- More secure (no password stored in the Actor)
- Bypasses 2FA requirement
- Session persists until you log out from browser
- Easy to update when needed

## Error Handling

The Actor automatically handles common Instagram errors:

### Common Error Types & Solutions

| Error Type | Description | Solution |
|-----------|-------------|----------|
| `challenge_required` | Instagram requires verification/CAPTCHA | Use fresh session cookies from browser, enable proxy, reduce scraping rate |
| `rate_limit` | Too many requests | Increase `delayBetweenProfiles`, use proxies, reduce `maxVideosPerProfile` |
| `profile_not_found` | Profile doesn't exist | Verify username spelling |
| `private_profile` | Profile is private | Provide authentication and follow the account |
| `unauthorized` | Session expired | Refresh session cookies from your browser |
| `connection_error` | Network issue | Check internet connectivity, try again |

## Limitations

### Authentication
- **Stories require authentication**: Stories from private accounts or accounts you don't follow cannot be downloaded
- **Private accounts**: Require authentication and following to access content
- **Public content limitations**: Without authentication, you may encounter 401/403 rate limiting errors

### Instagram API Limitations
- **Rate limiting**: Instagram may rate limit requests. The Actor handles this gracefully but may slow down
- **Temporary blocks**: Excessive requests may result in temporary IP blocks from Instagram
- **Content availability**: Some videos may be unavailable or geo-restricted

### Technical Limitations
- **Video quality**: Downloads videos in the quality provided by Instagram's public API
- **Comments limit**: Limited to first 100 comments per post to avoid excessive rate limiting
- **Large files**: Very large video files may take longer to download to Key-Value Store

## Best Practices

1. **Start small**: Test with a small number of profiles and videos first
2. **Use date filters**: When scraping accounts with many posts, use date filters to limit scope
3. **Monitor rate limits**: If you encounter rate limiting, reduce the number of profiles or videos
4. **Storage considerations**: Use `dataset_urls` method if you only need metadata and video links
5. **Respect Instagram's ToS**: This Actor is for educational and research purposes

## Error Handling

The Actor handles various error scenarios:

- **Profile not found**: Records error in dataset and continues
- **Private profile**: Records error message and skips profile
- **Rate limiting**: Automatically handled by Instaloader with retries
- **Download failures**: Individual video download failures are logged but don't stop the Actor

All errors are logged and included in the output dataset with `download_status: "failed"` and an `error_message` field.

## Resources

- [Instaloader Documentation](https://instaloader.github.io/)
- [Apify SDK for Python](https://docs.apify.com/sdk/python)
- [Apify Platform Documentation](https://docs.apify.com/)

## License

This Actor is provided as-is for educational and research purposes. Users are responsible for complying with Instagram's Terms of Service and applicable laws.

## Support

This is an independent project and is not officially supported by Apify.

For issues or questions:
- Check the [Instaloader documentation](https://instaloader.github.io/) for Instagram scraping issues
- Review [Apify Actor development guide](https://docs.apify.com/platform/actors/development) for Actor-related questions
- Open an issue on the GitHub repository for bugs or feature requests
