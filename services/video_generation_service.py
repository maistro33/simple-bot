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

    def _build_base_clip(
        self, scene_image_paths: list[Path], scene_durations: list[float], width: int, height: int
    ):
        """Build the concatenated, zoomed scene sequence shared by both render attempts."""
        clips = []
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
        return clips, concatenate_videoclips(clips, method="compose")

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
        Render the final MP4. Subtitle burn-in requires ImageMagick; if that
        fails for any environment-specific reason, we degrade gracefully to
        a captionless video rather than failing the whole pipeline — a
        finished silent/caption-less video is far more useful than none.
        """
        if not scene_image_paths:
            raise AIServiceError("Cannot assemble a video with zero scene images.")
        if len(scene_image_paths) != len(scene_durations):
            raise AIServiceError("scene_image_paths and scene_durations must be the same length.")

        width, height = resolution
        output_path.parent.mkdir(parents=True, exist_ok=True)

        clips, video = self._build_base_clip(scene_image_paths, scene_durations, width, height)
        text_clips: list = []

        try:
            try:
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
                        text_clips.append(text_clip)
                        overlays.append(text_clip)

                final = CompositeVideoClip(overlays, size=(width, height))
            except Exception as subtitle_exc:
                # ImageMagick missing/misconfigured, or any other subtitle
                # rendering failure — fall back to a captionless video.
                logger.warning(
                    "Subtitle burn-in failed ({}); rendering video without captions instead.", subtitle_exc
                )
                for tc in text_clips:
                    tc.close()
                text_clips = []
                final = CompositeVideoClip([video], size=(width, height))

            if voice_over_path and voice_over_path.exists():
                audio = AudioFileClip(str(voice_over_path))
                final = final.set_audio(audio)
                final = final.set_duration(min(final.duration, audio.duration))

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
            for tc in text_clips:
                tc.close()
