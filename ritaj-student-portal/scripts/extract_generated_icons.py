from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/assets/generated-icons/ritaj-icon-atlas.png"
OUTPUT = ROOT / "public/assets/generated-icons"

NAMES = [
    "graduation", "pencil", "search", "message", "chevron", "ellipsis",
    "panel-close", "trash", "menu", "arrow-right", "moon", "sun",
    "bell", "share", "refresh", "sparkle", "book", "check",
    "dollar", "clock", "copy", "thumbs-up", "thumbs-down", "paperclip",
    "microphone", "arrow-up", "calendar", "compass", "shield", "assistant",
]


def main() -> None:
    atlas = Image.open(ATLAS).convert("RGBA")
    cell_width = atlas.width / 6
    cell_height = atlas.height / 5

    for index, name in enumerate(NAMES):
        column = index % 6
        row = index // 6
        bounds = (
            round(column * cell_width),
            round(row * cell_height),
            round((column + 1) * cell_width),
            round((row + 1) * cell_height),
        )
        cell = atlas.crop(bounds)
        alpha_bounds = cell.getchannel("A").getbbox()
        if alpha_bounds is None:
            raise RuntimeError(f"No visible pixels found for {name}")

        icon = cell.crop(alpha_bounds)
        side = max(icon.width, icon.height)
        padding = max(8, round(side * 0.08))
        canvas_side = side + padding * 2
        canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
        canvas.alpha_composite(icon, ((canvas_side - icon.width) // 2, (canvas_side - icon.height) // 2))
        canvas = canvas.resize((128, 128), Image.Resampling.LANCZOS)
        canvas.save(OUTPUT / f"{name}.png", optimize=True)


if __name__ == "__main__":
    main()
