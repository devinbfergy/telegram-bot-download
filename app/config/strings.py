MESSAGES = {
    "start": (
        "<b>Video Downloader Bot is active!</b>\n\n"
        "I will automatically watch for messages containing video links from sites "
        "like YouTube, Instagram, and Facebook, and reply with the downloaded video. "
        "Just send a link in a message!"
    ),
    # Status messages
    "downloading": "📥 Downloading...",
    "processing": "⚙️ Processing...",
    "uploading": "⬆️ Uploading to Telegram...",
    "slideshow_building": "🛠️ Building slideshow video...",
    "gallery_dl_fallback": "🧩 Using gallery-dl as fallback...",
    "gallery_dl_processing": "🧩 Using gallery-dl for {purpose}...",
    # Alerts
    "tiktok_photo_alert": "🚨‼️ TIKTOK PHOTO ALERT ‼️🚨",
    "link_alert": "🚨‼️ LINK ALERT ‼️🚨",
    # Downloader specific messages
    "slideshow_detected": "Detected slideshow, using gallery-dl...",
    "frozen_frame_retry": "⚠️ Frozen frame video detected. Retrying with fallback...",
    "frozen_frame_failed": "❌ Fallback download is also a frozen video. Aborting.",
    "video_too_large": "❌ Video is too large ({file_size_mb:.2f}MB). Limit is {limit_mb}MB.",
    # Gallery-dl specific messages
    "gallery_dl_no_media": "❌ No media found via gallery-dl.",
    "gallery_dl_uploading_video": "⬆️ Uploading video (gallery-dl)...",
    "gallery_dl_uploading_slideshow": "⬆️ Uploading slideshow...",
    "gallery_dl_sending_images": "⬆️ Sending images (gallery-dl)...",
    "gallery_dl_no_suitable_media": "❌ No suitable media found to send.",
    "gallery_dl_error": "❌ gallery-dl error: {error}",
    # Bad bot reprocessing
    "reprocessing": "🔄 Reprocessing with better quality...",
    "reprocessing_no_url": "❌ Could not find URL in the original message.",
    # Generic errors
    "error_generic": "❌ An unexpected error occurred. Please try again later.",
    "error_no_text": "❌ Could not find any text in the original message.",
    "error_ai_features_not_configured": "❌ AI features are not configured.",
    "error_ai_api_request_failed": "❌ Failed to get a response from the AI. Please try again later.",
    "error_video_too_large": "❌ Error: The video is too large ({file_size_mb:.2f}MB). Telegram's limit for bot uploads is {limit_mb}MB.",
    "unsupported_url": "Unsupported or invalid URL.",
    # Good bot catgirl feature
    "error_catgirl_features_not_configured": "❌ Catgirl features are not configured (missing Gemini API key).",
    "error_catgirl_api_request_failed": "❌ Failed to get catgirl response. Nya~ something went wrong!",
    # GitHub issue feature
    "github_issue_fetching_messages": "📝 Fetching recent messages...",
    "github_issue_summarizing": "🤖 Summarizing conversation...",
    "github_issue_creating": "🐙 Creating GitHub issue...",
    "github_issue_created": "✅ GitHub issue created: {url}",
    "error_github_not_configured": "❌ GitHub integration is not configured. Set GITHUB_TOKEN and GITHUB_REPO environment variables.",
    "error_github_api_failed": "❌ Failed to create GitHub issue. Please try again later.",
    "error_github_no_messages": "❌ Could not find any messages to create an issue from.",
    "error_github_summarization_failed": "❌ Failed to summarize the conversation. Please try again later.",
    "guys_being_dudes_response": "sup dude 🤙",
    # Mention responder (generic @gork / @guys_being_dudes_bot mentions)
    "error_mention_responder_not_configured": "❌ Mention responder not configured (missing Gemini API key).",
    "error_mention_responder_api_failed": "❌ Failed to get a response. Try again later.",
}
