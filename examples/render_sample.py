"""Generate a synthetic narration + MFA-style TextGrid, then render it. Run from the repo root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tests" / "fixtures"))
import make_fixtures  # noqa: E402

from storyframe import RenderConfig, render_video  # noqa: E402

out = Path("sample_out")
paths = make_fixtures.write_all(out)
res = render_video(paths["audio"], paths["textgrid"], out / "story.mp4", RenderConfig(), paths["transcript"], overwrite=True,
                   progress=lambda stage, f: print(f"{stage}: {f:.0%}", end="\r"))
print(res.output_path, f"{res.duration:.2f}s", res.resolution, res.verification)
