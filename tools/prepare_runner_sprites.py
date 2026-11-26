"""Build the transparent walking and flying cycles used by both pet surfaces."""
from math import cos, sin, tau
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
from PIL.PngImagePlugin import PngInfo


ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'runner'
CELL = 128
ART_SCALE = 1.10
# Numbers are source poses in playback order and the clearance of each sole, in
# fractions of the drawing width. A zero means the paw touches the ground line.
POSES = {
    'cat': ((0, 1, 2, 3, 4, 5, 6, 7), (0, 0, .025, 0, 0, .025, .095, .055)),
    'dog': ((0, 1, 2, 3, 4, 5, 6, 7), (0, 0, .012, .033, 0, 0, .012, .033)),
    'rabbit': ((0, 7, 1, 2, 3, 4, 5, 6), (.025, 0, 0, 0, 0, 0, .040, .12)),
    # Use only airborne illustrations from the selected bird sheet. Register
    # each wing beat at a different height so the body keeps hovering.
    'bird': ((2, 3, 4, 2, 5, 5, 2, 3), (.10, .05, .03, .06, .13, .20, .22, .17)),
    'penguin': (tuple(range(48)), (0,) * 48),
}


def penguin_walk(atlas, count):
    """Two alternating steps seen from the penguin's right-facing profile."""
    scale = 3
    limb_scale = 1.20
    canvas = (CELL * scale,) * 2
    width, height = atlas.size

    def part(box):
        drawing = atlas.crop(box)
        # Discard the almost invisible matte outside the ink. Solid fills in
        # the master are just below 255, so restore their intended opacity.
        alpha = drawing.getchannel('A').point(lambda a: 0 if a < 4 else 255 if a >= 249 else a)
        drawing.putalpha(alpha)
        return drawing.crop(alpha.getbbox())

    body = part((0, 0, width // 2, height))
    body = body.resize((80 * scale, 110 * scale), Image.Resampling.LANCZOS)
    neutral = Image.new('RGBA', canvas)
    neutral.alpha_composite(body, (24 * scale, 5 * scale))
    wings, feet = {}, {}
    for side, col in ((-1, 2), (1, 3)):
        left, right = width * col // 4, width * (col + 1) // 4
        wings[side] = part((left, 0, right, height * 3 // 5))
        feet[side] = part((left, height * 3 // 5, right, height))
    # Fade the near flipper's upper seam into the flank at its shoulder.
    near_wing = wings[-1]
    seam = Image.new('L', (1, near_wing.height))
    seam.putdata([min(255, round(255 * y / (.23 * near_wing.height))) for y in range(near_wing.height)])
    near_wing.putalpha(ImageChops.multiply(near_wing.getchannel('A'), seam.resize(near_wing.size)))

    # This is a side elevation. Weight transfer is toward/away from the viewer.
    # Keep the forward lean, head and belly fixed for the entire walk.
    pivot = (62 * scale, 112 * scale)
    torso = neutral.rotate(-5, Image.Resampling.BICUBIC, center=pivot)
    red, green, blue, alpha = wings[1].split()
    wings[1] = Image.merge('RGBA', (red.point(lambda v: round(v * .84)),
                                    green.point(lambda v: min(255, round(v * 1.15))),
                                    blue.point(lambda v: min(255, round(v * 1.10))), alpha))

    def resize_limb(drawing, width, height):
        size = (round(width * limb_scale * scale), round(height * limb_scale * scale))
        return drawing.resize(size, Image.Resampling.LANCZOS)

    def hinged_wing(side):
        near = side == -1
        size = (28, 37) if near else (39, 50)
        wing = resize_limb(wings[side], *size)
        # The original flippers point diagonally in opposite directions. Set
        # each one vertical before measuring its fore/aft swing at the joint.
        # Keep the front of the belly visible throughout the near flipper's forward stroke.
        shoulder = (50, 66) if near else (63, 65)
        joint = tuple(coord * scale for coord in shoulder)
        # Tuck the far flipper's root into the shoulder so its longer tip
        # clears the planted foot at the bottom of its swing.
        socket_x, socket_y = (.84, .14) if near else (.16, .28)
        layer = Image.new('RGBA', canvas)
        layer.alpha_composite(wing, (joint[0] - round(wing.width * socket_x),
                                     joint[1] - round(wing.height * socket_y)))
        return layer, joint, 35 if near else -36

    mounts = {side: hinged_wing(side) for side in (-1, 1)}
    shoes = {-1: resize_limb(feet[-1], 26, 13), 1: resize_limb(feet[1], 23, 11)}
    for index in range(count):
        phase = tau * index / count
        stride, step = cos(phase), sin(phase)

        def wing_pose(side):
            layer, joint, vertical = mounts[side]
            angle = vertical + side * (47 if side == -1 else 53) * stride
            return layer.rotate(angle, Image.Resampling.BICUBIC, center=joint)

        def foot_pose(side):
            near = side == -1
            forward = -side * stride
            lift = max(0., side * step)
            sole = 122 - 6.8 * lift * lift
            ankle_x = (55 if near else 62) + 10.4 * forward
            foot = shoes[side].rotate((13 * forward + 3) * lift, Image.Resampling.BICUBIC, expand=True)
            foot = foot.crop(foot.getchannel('A').getbbox())
            # Enlarge the toe around the ankle while keeping the planted sole on the ground.
            center = ankle_x + 5 * limb_scale
            pos = (round(center * scale - foot.width / 2), round(sole * scale - foot.height))
            ankle = (round(ankle_x * scale), round((sole - 6) * scale))
            return foot, pos, ankle

        far_foot, far_pos, far_ankle = foot_pose(1)
        near_foot, near_pos, near_ankle = foot_pose(-1)
        frame = wing_pose(1)
        legs = ImageDraw.Draw(frame)
        for hip, ankle in (((65, 108), far_ankle), ((59, 109), near_ankle)):
            legs.line(((hip[0] * scale, hip[1] * scale), ankle), fill='#282531', width=4 * scale)
        frame.alpha_composite(far_foot, far_pos)
        frame.alpha_composite(torso)
        frame.alpha_composite(near_foot, near_pos)
        frame.alpha_composite(wing_pose(-1))
        yield frame


def prepare(animal):
    order, clearance = POSES[animal]
    frames, bounds = [], []
    filename = 'penguin-right-parts' if animal == 'penguin' else animal
    with Image.open(ASSETS / 'original' / (filename + '.png')) as source:
        if animal == 'cat':
            # Store the calico's white coat as opaque #FFFFFF. Keep antialiased edges.
            red, green, blue, alpha = source.split()
            light = ImageChops.darker(red, ImageChops.darker(green, blue))
            white = light.point(lambda value: 255 if value >= 238 else 0)
            interior = alpha.point(lambda value: 255 if value >= 240 else 0)
            source.paste((255, 255, 255, 255), mask=ImageChops.darker(white, interior))
        if animal == 'penguin':
            frames = list(penguin_walk(source, len(order)))
        else:
            for index in order:
                col, row = index % 4, index // 4
                frames.append(source.crop((round(col * source.width / 4), round(row * source.height / 2),
                                           round((col+1) * source.width / 4), round((row+1) * source.height / 2))))
        for index, cell in enumerate(frames):
            # Nearly transparent fringe pixels must not move the registration point.
            box = cell.getchannel('A').point(lambda alpha: 255 if alpha >= 32 else 0).getbbox()
            if box is None:
                raise ValueError(f'Empty {animal} pose {index}')
            bounds.append(box)
    if animal == 'penguin':
        # The puppet already has a shared ground line. Use one crop and one
        # sampling grid so a moving wing cannot recenter the stationary body.
        union = (min(b[0] for b in bounds), min(b[1] for b in bounds),
                 max(b[2] for b in bounds), max(b[3] for b in bounds))
        bounds = [union] * len(frames)
    left = min(box[0] for box in bounds)
    width = max(box[2] for box in bounds) - left
    height = max(box[3] - box[1] + lift * width for box, lift in zip(bounds, clearance))
    # All poses get one scale. Fitting each pose separately would stretch
    # the animal as it collects and extends its legs.
    scale = (.885 * ART_SCALE * CELL) / max(width, height)
    origin = (CELL - width * scale) / 2
    ground = (CELL + height * scale) / 2
    columns = 8 if animal == 'penguin' else 4
    sheet = Image.new('RGBA', (columns * CELL, (len(frames)//columns) * CELL))
    tray_inset = CELL // 2
    for i, (cell, box, lift) in enumerate(zip(frames, bounds, clearance)):
        x1, y1, x2, y2 = box
        drawing = cell.crop((x1 - 2, y1 - 2, x2 + 2, y2 + 2))
        size = tuple(round(length * scale) for length in drawing.size)
        drawing = drawing.resize(size, Image.Resampling.LANCZOS)
        x = round(origin + (x1 - 2 - left) * scale)
        y = round(ground + (y1 - 2 - y2 - lift * width) * scale)
        frame = Image.new('RGBA', (CELL, CELL))
        frame.alpha_composite(drawing, (x, y))
        sheet.paste(frame, ((i % columns) * CELL, (i // columns) * CELL))
        x_min, y_min, x_max, y_max = frame.getchannel('A').getbbox()
        tray_inset = min(tray_inset, x_min, y_min, CELL - x_max, CELL - y_max)
    # Remove only padding shared by every pose. The capsule uses the full tile.
    metadata = PngInfo()
    metadata.add_text('TrayInset', str(tray_inset))
    sheet.save(ASSETS / (animal + '.png'), pnginfo=metadata, optimize=True)


if __name__ == '__main__':
    for name in POSES:
        prepare(name)
