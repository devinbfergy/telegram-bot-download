import logging
import os
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def create_slideshow_from_media(
    image_paths: List[Path], audio_path: Path, output_path: Path
) -> bool:
    """
    Creates an MP4 slideshow video from a list of images and an audio file.

    This function uses FFmpeg to:
    1. Probe the audio duration to determine the display time for each image.
    2. Normalize all input images to JPEG format.
    3. Create a video from the image sequence.
    4. Mux the video with the provided audio.

    Args:
        image_paths: A list of Path objects for the input images.
        audio_path: A Path object for the input audio file.
        output_path: The Path where the final video will be saved.

    Returns:
        True if the slideshow was created successfully, False otherwise.
    """
    if not image_paths:
        logger.warning("No images provided for slideshow creation.")
        return False

    temp_dir = output_path.parent
    slides_dir = temp_dir / "normalized_slides"
    slides_dir.mkdir(exist_ok=True)

    try:
        # 1. Probe audio duration
        try:
            probe_cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ]
            result = subprocess.run(
                probe_cmd, capture_output=True, text=True, timeout=15, check=True
            )
            audio_duration = float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            logger.warning(
                "Could not probe audio duration. Falling back to default duration."
            )
            audio_duration = 2.0 * len(image_paths)

        per_image_duration = max(0.5, min(8.0, audio_duration / len(image_paths)))

        # 2. Normalize images
        normalized_image_paths = []
        for idx, img_path in enumerate(image_paths):
            target_path = slides_dir / f"frame_{idx:04d}.jpg"
            if img_path.suffix.lower() in (".jpg", ".jpeg"):
                target_path.write_bytes(img_path.read_bytes())
            else:
                # Convert non-JPEG images to JPEG using FFmpeg
                convert_cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(img_path), str(target_path)]
                subprocess.run(convert_cmd, check=True, timeout=30)
            normalized_image_paths.append(target_path)

        # 3. Create video from frames
        framerate = 1.0 / per_image_duration
        temp_video_path = temp_dir / "slideshow_no_audio.mp4"
        video_cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-framerate",
            f"{framerate:.4f}",
            "-i",
            str(slides_dir / "frame_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temp_video_path),
        ]
        subprocess.run(video_cmd, check=True, timeout=300)

        # 4. Mux video and audio
        mux_cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(temp_video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        subprocess.run(mux_cmd, check=True, timeout=300)

        return output_path.exists()

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg command failed: {e.cmd} with output: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during slideshow creation: {e}")
        return False
