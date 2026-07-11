"""Generate simple synthetic PNG images for testing image ingestion."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

images = [
    ("architecture_diagram.png", "Architecture Diagram", (52, 100, 180)),
    ("onboarding_flowchart.png", "Onboarding Flowchart", (34, 150, 100)),
]

for filename, label, color in images:
    img = Image.new("RGB", (400, 300), color=color)
    draw = ImageDraw.Draw(img)
    # Simple text label
    draw.rectangle([20, 20, 380, 280], outline=(255,255,255), width=3)
    draw.text((40, 130), label, fill=(255, 255, 255))
    # Add some shapes to make it non-trivial
    for _ in range(5):
        x1, y1 = random.randint(40, 200), random.randint(40, 150)
        x2, y2 = x1 + random.randint(20, 80), y1 + random.randint(20, 60)
        draw.rectangle([x1, y1, x2, y2], outline=(200, 200, 200))
    path = OUTPUT_DIR / filename
    img.save(path)
    print(f"Created: {path}")

print("Done.")
