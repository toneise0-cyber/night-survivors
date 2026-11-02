"""Make the pictures in assets/ from the originals in raw_art/.

Run this script yourself, never from the game:

    python make_assets.py

raw_art/ is never changed. Every sprite is made SCALE times bigger with the
nearest neighbour filter, so the pixels stay sharp instead of getting blurry.
"""

import os

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw_art")
ASSETS = os.path.join(ROOT, "assets")
SCALE = 3

# every original picture that the game draws, with the same name in assets/
SPRITES = ("bat.png", "demon.png", "floor.png", "ghost.png", "hero.png",
           "slime.png", "sword.png")

# the two crystal gems, coloured from raw_art/gem.png:
# the dark side, the main colour and the bright side of the stone
GEMS = {
    "gem_blue.png": ((16, 44, 96), (90, 169, 255), (235, 248, 255)),
    "gem_pink.png": ((112, 16, 78), (255, 122, 217), (255, 236, 250)),
}


def grow(image):
    """SCALE times bigger, no blurring."""
    return image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)


def read_raw(name):
    with Image.open(os.path.join(RAW, name)) as handle:
        return handle.convert("RGBA")


def crystal(gem, colours):
    """Keep the shape of the gem, but colour it like a bright stone."""
    dark, middle, bright = colours
    red, green, blue, alpha = gem.split()
    shading = Image.merge("RGB", (red, green, blue)).convert("L")
    face = ImageOps.colorize(shading, black=dark, white=bright, mid=middle)
    stone = face.convert("RGBA")
    stone.putalpha(alpha)
    return stone


def save(image, name):
    image.save(os.path.join(ASSETS, name))
    print("assets/{}  {} x {} px".format(name, image.width, image.height))


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for name in SPRITES:
        save(grow(read_raw(name)), name)
    gem = grow(read_raw("gem.png"))
    for name, colours in GEMS.items():
        save(crystal(gem, colours), name)
    print("done: {} pictures in assets/".format(len(SPRITES) + len(GEMS)))


if __name__ == "__main__":
    main()
