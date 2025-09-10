class DownloadError(Exception):
    """Base download error."""

class UnsupportedURLError(DownloadError):
    pass

class ExtractionFailed(DownloadError):
    pass

class PostProcessError(DownloadError):
    pass

class SendError(DownloadError):
    pass

class SizeLimitExceeded(DownloadError):
    pass
