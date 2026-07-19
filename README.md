# Fact Drop AI Studio

**AI-powered affiliate content creation platform.** Feed it a product URL, title,
or description — it researches the market, builds a marketing strategy, writes
a YouTube Shorts script, storyboards it, generates cinematic AI prompts,
synthesises a voice-over, burns subtitles, designs thumbnails, produces a full
SEO package, renders the final vertical video, writes a quality report, and
exports everything into a single delivery bundle. Fully automated, end to end.

## Pipeline

```
Product Input
     │
     ▼
1. Product Analysis        ┐
2. Category Detection      │
3. Brand Detection         ├─ Research Engine
4. Competitor Research     │
5. Audience Analysis       ┘
     │
     ▼
6. Marketing Strategy      ── Strategy Engine
     │
     ▼
7. Hook Generation         ┐
8. Script Generation       ┘─ Script Engine
     │
     ▼
9. Storyboard Generation   ── Storyboard Engine
     │
     ▼
10. Cinematic AI Prompts   ── Prompt Engine
     │
     ▼
11. Voice Generation       ── Voice Engine (ElevenLabs)
     │
     ▼
12. Subtitle Generation    ── Subtitle Engine (SRT/VTT)
     │
     ▼
13. Thumbnail Generation   ── Thumbnail Engine (OpenAI images)
     │
     ▼
14. SEO Package             ── SEO Engine
     │
     ▼
15. Report Generation       ── Report Engine + Quality Engine
     │
     ▼
16. Video Assembly + Export ── Video Engine (MoviePy) + Export Manager
     │
     ▼
  Finished — full ZIP bundle in exports/
```

## Architecture

Clean, layered, SOLID architecture:

```
config/       Type-safe settings (pydantic-settings) + shared constants/enums
database/     SQLAlchemy 2.0 models (14 tables) + Repository pattern
core/         Infrastructure: logging, event bus, cache, queue, scheduler,
              settings/asset/backup/recovery/export/project managers,
              the Workflow Engine orchestrator, and the Application facade
engines/      12 pipeline engines (Research, Strategy, Script, Storyboard,
              Prompt, Voice, Subtitle, Thumbnail, SEO, Report, Quality, Video)
services/     External API integrations: OpenAI, ElevenLabs, YouTube Data API,
              image/video generation, all behind the AIManager facade
plugins/      Platform product-data extraction: Amazon, AliExpress, Temu,
              eBay, Shopify, YouTube, TikTok — routed via PluginRegistry
tests/        Unit + a full end-to-end integration test (mocked AI/media)
```

Every engine depends only on the `AIManager` abstraction (constructor
injection), never on a concrete SDK — this is what makes the 42-test suite,
including a full 16-stage pipeline run, executable without any live API keys.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env and set at minimum OPENAI_API_KEY
```

FFmpeg must be installed and on your `PATH` for video assembly (MoviePy
depends on it):

```bash
# Debian/Ubuntu
sudo apt install ffmpeg
# macOS
brew install ffmpeg
# Windows
choco install ffmpeg
```

### Required / optional credentials

| Variable | Required for | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Every text/JSON/image generation stage | Required for any real run |
| `ELEVENLABS_API_KEY` | Voice-over synthesis | Without it, the pipeline still completes — it just skips audio and records duration only |
| `YOUTUBE_API_KEY` | Real competitor video research | Without it, the Research Engine relies purely on AI-estimated competitor insights |
| `VIDEO_PROVIDER` | Scene visual generation | `none`/`openai` (default) uses AI still images animated with Ken Burns zoom; `runway`/`pika` are wired as extension points |

## Usage

```bash
# Run the full pipeline for a new product
python main.py create "https://www.amazon.com/dp/B0EXAMPLE"
python main.py create "A stainless steel self-stirring travel mug with USB charging" --name "Stirring Mug"

# List projects
python main.py list

# Inspect one project
python main.py show <project_id>

# Resume an interrupted/failed project from its last completed stage
python main.py resumable
python main.py resume <project_id>

# Export a completed project's full bundle
python main.py export <project_id> --format zip

# Undo the most recent change to a project
python main.py undo <project_id>

# List disaster-recovery backups
python main.py backups <project_id>

# Delete a project (and its on-disk assets)
python main.py delete <project_id> --yes
```

Every command also works via `python -m main <command>` or, if you install the
package, the `fact-drop-ai` console script.

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

The suite includes a full end-to-end integration test
(`tests/integration/test_full_pipeline.py`) that drives a project through
**every single one of the 16 pipeline stages** via the real `WorkflowEngine`,
with only the external network boundaries (AI completions, image generation,
video rendering) replaced by deterministic fakes — proving the whole system
is correctly wired without needing live credentials in CI.

## Extending

- **New platform plugin**: subclass `plugins.base_plugin.PlatformPlugin`,
  implement `matches()`/`fetch_product_data()`, register it in
  `plugins/plugin_registry.py`. No other code needs to change (Open/Closed).
- **New video provider**: extend `VideoGenerationService.generate_scene_visual`
  with a new `elif provider == "your_provider":` branch.
- **New engine/stage**: subclass `engines.base_engine.BaseEngine`, implement
  `execute()`, register it in `core/workflow_engine.py`'s `_STAGE_ENGINE_ORDER`
  and `_stage_handlers`.

## License

See [LICENSE](LICENSE).
