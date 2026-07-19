"""
Video Generation Service — provider-agnostic video creation.

Two responsibilities:
  1. Delegate scene-level AI video/image generation to a configurable
     provider backend (currently ``openai`` image stills; ``runway``/
     ``pika`` are wired as extension points via the Strategy pattern).
  2. Locally assemble the final vertical video (images + voice-over +
     burned-in subtitles) using MoviePy + ffmpeg, which works completely
     offline once scene images and the voice-over audio exist.
"""
from __future__ import annotations

from pathlib import Path

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)

from config import get_settings
from core.exceptions import AIServiceError, ConfigurationError
from core.logger import get_logger
from services.image_generation_service import ImageGenerationService

logger = get_logger(__name__)


class VideoGenerationService:
    """
    Assembles a finished vertical (9:16) video from per-scene images, a
    single voice-over audio track, and subtitle cues, and exposes a
    provider hook for future true AI video-clip generation.
    """

    def __init__(self, image_service: ImageGenerationService | None = None) -> None:
        self._settings = get_settings()
        self._image_service = image_service or ImageGenerationService()

    def generate_scene_visual(self, prompt: str, aspect_ratio: str = "9:16") -> bytes:
        """
        Produce the visual for one storyboard scene.

        With ``VIDEO_PROVIDER=none`` or ``openai`` (the default), this
        falls back to a still image generated via the Image Generation
        Service, which MoviePy then animates with a subtle Ken Burns
        zoom during assembly. When ``runway``/``pika`` API keys are
        configured, this is the extension point where a true video clip
        would be requested instead.
        """
        provider = self._settings.video_provider
        if provider in ("none", "openai"):
            return self._image_service.generate(prompt, aspect_ratio=aspect_ratio)
        if provider == "runway":
            if not self._settings.runway_api_key:
                raise ConfigurationError("VIDEO_PROVIDER=runway but RUNWAY_API_KEY is not set.")
            raise AIServiceError(
                "Runway video generation is configured but not yet implemented in this build; "
                "falling back is disabled to avoid silently producing the wrong output. "
                "Set VIDEO_PROVIDER=openai to use image-based scene generation."
            )
        if provider == "pika":
            if not self._settings.pika_api_key:
                raise ConfigurationError("VIDEO_PROVIDER=pika but PIKA_API_KEY is not set.")
            raise AIServiceError(
                "Pika video generation is configured but not yet implemented in this build; "
                "set VIDEO_PROVIDER=openai to use image-based scene generation."
            )
        raise ConfigurationError(f"Unknown VIDEO_PROVIDER '{provider}'.")

    def assemble_video(
        self,
        scene_image_paths: list[Path],
        scene_durations: list[float],
        voice_over_path: Path | None,
        subtitle_cues: list[dict] | None,
        output_path: Path,
        fps: int = 30,
        resolution: tuple[int, int] = (1080, 1920),
    ) -> Path:
        """
        Render the final MP4 by concatenating scene images (each held for
        its scripted duration with a gentle zoom), overlaying the voice-over
        track and burning in subtitle cues.

        Args:
            scene_image_paths: Ordered list of image file paths, one per scene.
            scene_durations: Matching list of on-screen durations (seconds).
            voice_over_path: Path to the synthesised narration audio, or None.
            subtitle_cues: List of ``{"start": float, "end": float, "text": str}``.
            output_path: Destination ``.mp4`` file path.
            fps: Output frame rate.
            resolution: ``(width, height)`` output resolution.

        Returns:
            The path to the rendered video file.

        Raises:
            AIServiceError: If no scene images are supplied, or rendering fails.
        """
        if not scene_image_paths:
            raise AIServiceError("Cannot assemble a video with zero scene images.")
        if len(scene_image_paths) != len(scene_durations):
            raise AIServiceError("scene_image_paths and scene_durations must be the same length.")

        width, height = resolution
        clips = []
        try:
            for image_path, duration in zip(scene_image_paths, scene_durations):
                clip = (
                    ImageClip(str(image_path))
                    .set_duration(max(duration, 0.5))
                    .resize(height=height)
                )
                if clip.w > width:
                    clip = clip.crop(x_center=clip.w / 2, width=width)
                clip = clip.resize(lambda t, c=clip: 1.0 + 0.04 * (t / max(c.duration, 0.01)))
                clips.append(clip)

            video = concatenate_videoclips(clips, method="compose")

            overlays: list = [video]
            if subtitle_cues:
                for cue in subtitle_cues:
                    text_clip = (
                        TextClip(
                            cue["text"],
                            fontsize=64,
                            color="white",
                            stroke_color="black",
                            stroke_width=3,
                            method="caption",
                            size=(int(width * 0.9), None),
                        )
                        .set_start(cue["start"])
                        .set_end(cue["end"])
                        .set_position(("center", "bottom"))
                    )
                    overlays.append(text_clip)

            final = CompositeVideoClip(overlays, size=(width, height))

            if voice_over_path and voice_over_path.exists():
                audio = AudioFileClip(str(voice_over_path))
                final = final.set_audio(audio)
                final = final.set_duration(min(final.duration, audio.duration))

            output_path.parent.mkdir(parents=True, exist_ok=True)
            final.write_videofile(
                str(output_path),
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                threads=4,
                logger=None,
            )
            logger.info("Assembled video at {}", output_path)
            return output_path
        except Exception as exc:  # noqa: BLE001 - MoviePy/ffmpeg raise assorted errors
            raise AIServiceError(f"Video assembly failed: {exc}") from exc
        finally:
            for clip in clips:
                clip.close()
