"""Register the approved eight-pose illustrations for the tray and capsule."""
from pathlib import Path

from PIL import Image


ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'runner'
CELL = 128
ART_SCALE = 1.10
# Numbers are source poses in playback order and the clearance of each sole, in
# fractions of the drawing width. A zero means the paw touches the ground line.
POSES = {
    'cat': ((0, 1, 2, 3, 4, 5, 6, 7), (0, 0, .025, 0, 0, .025, .095, .055)),
    'dog': ((0, 1, 2, 3, 4, 5, 6, 7), (0, 0, .012, .033, 0, 0, .012, .033)),
    'rabbit': ((0, 7, 1, 2, 3, 4, 5, 6), (.025, 0, 0, 0, 0, 0, .040, .12)),
}


def prepare(animal):
    order, clearance = POSES[animal]
    frames, bounds = [], []
    with Image.open(ASSETS / 'original' / (animal + '.png')) as source:
        for index in order:
            col, row = index % 4, index // 4
            cell = source.crop((round(col * source.width / 4), round(row * source.height / 2),
                                round((col+1) * source.width / 4), round((row+1) * source.height / 2)))
            # Nearly transparent fringe pixels must not move the registration point.
            box = cell.getchannel('A').point(lambda alpha: 255 if alpha >= 32 else 0).getbbox()
            if box is None:
                raise ValueError(f'Empty {animal} pose {index}')
            frames.append(cell)
            bounds.append(box)
    left = min(box[0] for box in bounds)
    width = max(box[2] for box in bounds) - left
    height = max(box[3] - box[1] + lift * width for box, lift in zip(bounds, clearance))
    # All eight poses get one scale. Fitting each pose separately would stretch
    # the animal as it collects and extends its legs.
    scale = (.885 * ART_SCALE * CELL) / max(width, height)
    origin = (CELL - width * scale) / 2
    ground = (CELL + height * scale) / 2
    sheet = Image.new('RGBA', (4 * CELL, 2 * CELL))
    for i, (cell, box, lift) in enumerate(zip(frames, bounds, clearance)):
        x1, y1, x2, y2 = box
        drawing = cell.crop((x1 - 2, y1 - 2, x2 + 2, y2 + 2))
        size = tuple(round(length * scale) for length in drawing.size)
        drawing = drawing.resize(size, Image.Resampling.LANCZOS)
        x = round(origin + (x1 - 2 - left) * scale)
        y = round(ground + (y1 - 2 - y2 - lift * width) * scale)
        frame = Image.new('RGBA', (CELL, CELL))
        frame.alpha_composite(drawing, (x, y))
        sheet.paste(frame, ((i % 4) * CELL, (i // 4) * CELL))
    sheet.save(ASSETS / (animal + '.png'), optimize=True)


if __name__ == '__main__':
    for name in POSES:
        prepare(name)
