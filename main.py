"""The window, the drawing and the input of Night Survivors.

The rules live in rules.py. This file only turns the mouse or finger into a
walk target or a card choice, calls rules.step() with a fixed time step, and
paints the result with the finished pictures from assets/.
"""

import asyncio
import math
import os

import pygame

import rules


def format_time(ticks, ticks_per_second):
    """7200 ticks at 60 ticks a second is 120 seconds, so "2:00"."""
    whole = int(ticks / ticks_per_second)
    return "{}:{:02d}".format(whole // 60, whole % 60)


def color(name):
    return pygame.Color(name)


class Art:
    """The pictures from assets/, loaded once and kept at the size they are drawn.

    This class only reads finished files, so it also works in a web browser.
    """

    def __init__(self, cfg):
        self.folder = cfg["art"]["folder"]
        self.by_name = {}
        self.by_size = {}

    def sprite(self, name, size_px):
        """The picture for name, as a square of size_px pixels."""
        key = (name, size_px)
        if key not in self.by_size:
            image = self.load(name)
            if image.get_width() == size_px:
                self.by_size[key] = image
            else:
                self.by_size[key] = pygame.transform.scale(image, (size_px, size_px))
        return self.by_size[key]

    def load(self, name):
        if name not in self.by_name:
            path = os.path.join(self.folder, name)
            try:
                self.by_name[name] = pygame.image.load(path).convert_alpha()
            except (OSError, pygame.error):
                raise SystemExit("No picture at {}. Run make_assets.py once.".format(path))
        return self.by_name[name]


class Game:
    def __init__(self, cfg):
        self.cfg = cfg
        self.world = rules.new_world(cfg)
        self.width = cfg["window"]["width_px"]
        self.height = cfg["window"]["height_px"]
        self.art = Art(cfg)
        self.floor_shade = self.make_floor_shade()
        self.fonts = {}
        # Walk target on the screen. On a computer the mouse is the target all
        # the time; on a phone only a finger that touches the screen is.
        # (0, 0) means "the browser does not know the mouse yet".
        self.mouse_px = pygame.mouse.get_pos() or None
        self.finger_px = None
        self.used_finger = False

    def make_floor_shade(self):
        """A see-through square to make every other floor tile a bit darker."""
        floor = self.cfg["floor"]
        shade = pygame.Surface((floor["tile_px"], floor["tile_px"]), pygame.SRCALPHA)
        tint = color(floor["checker_color"])
        shade.fill((tint.r, tint.g, tint.b, floor["checker_alpha"]))
        return shade

    # ---------- input ----------

    def handle(self, event):
        """One pygame event. Returns False when the player closes the window."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_p:
                self.world["paused"] = not self.world["paused"]
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            self.mouse_px = event.pos
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.tap(*event.pos)
        if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            self.used_finger = True
            # finger positions are fractions of the window, not pixels
            lifted = event.type == pygame.FINGERUP
            self.finger_px = None if lifted else (event.x * self.width, event.y * self.height)
            if not lifted:
                self.tap(*self.finger_px)
        return True

    def tap(self, px, py):
        """A click or a tap: pick a card, or start again on the end screen."""
        if self.world["state"] == "choosing":
            for index, place in enumerate(self.card_rects()):
                if place.collidepoint(px, py):
                    rules.choose_card(self.world, index)
                    return
        elif self.world["state"] in ("game_over", "victory"):
            self.world = rules.new_world(self.cfg)

    # ---------- walking ----------

    def camera(self):
        """Top-left corner of the part of the world we can see."""
        hero = self.world["hero"]
        return (hero["x"] - self.width / 2, hero["y"] - self.height / 2)

    def walk_target(self):
        """Where the hero walks to, in world coordinates, or None to stand still."""
        if self.finger_px is not None:
            px, py = self.finger_px
        elif self.used_finger or self.mouse_px is None:
            return None  # a finger lifted on a phone, or no pointer yet
        else:
            px, py = self.mouse_px
        left, top = self.camera()
        return (px + left, py + top)

    # ---------- one frame ----------

    def step_rules(self):
        rules.step(self.world, self.walk_target())

    def draw(self, screen):
        camera = self.camera()
        self.draw_floor(screen, camera)
        self.draw_holy_ring(screen, camera)
        for gem in self.world["gems"]:
            self.draw_gem(screen, gem, camera)
        for enemy in self.world["enemies"]:
            self.draw_enemy(screen, enemy, camera)
        for spark in self.world["sparks"]:
            self.draw_spark(screen, spark, camera)
        self.draw_blades(screen, camera)
        self.draw_hero(screen, camera)
        self.draw_hud(screen)
        if self.world["state"] == "choosing":
            self.draw_cards(screen)
        elif self.world["state"] in ("game_over", "victory"):
            hero = self.world["hero"]
            title = "VICTORY" if self.world["state"] == "victory" else "GAME OVER"
            self.draw_banner(screen, title, [
                "time {}   kills {}   Lv {}".format(
                    self.time_text(), self.world["kills"], hero["level"]),
                "click or tap to play again",
            ])
        elif self.world["paused"]:
            self.draw_banner(screen, "PAUSED", ["press P to continue"])

    def to_screen(self, x, y, camera):
        return (int(round(x - camera[0])), int(round(y - camera[1])))

    def draw_floor(self, screen, camera):
        """One tile repeated forever, so the map has no edges."""
        floor = self.cfg["floor"]
        tile = floor["tile_px"]
        image = self.art.sprite(floor["sprite"], tile)
        row = 0
        y = math.floor(camera[1] / tile) * tile
        while y < camera[1] + self.height:
            col = 0
            x = math.floor(camera[0] / tile) * tile
            while x < camera[0] + self.width:
                spot = self.to_screen(x, y, camera)
                screen.blit(image, spot)
                if (row + col) % 2:
                    screen.blit(self.floor_shade, spot)
                col += 1
                x += tile
            row += 1
            y += tile

    def draw_hero(self, screen, camera):
        hero = self.world["hero"]
        cfg = self.cfg["hero"]
        image = self.art.sprite(cfg["sprite"], cfg["sprite_px"])
        screen.blit(image, image.get_rect(center=self.to_screen(hero["x"], hero["y"], camera)))

    def draw_enemy(self, screen, enemy, camera):
        cfg = self.cfg[enemy["kind"]]
        image = self.art.sprite(cfg["sprite"], cfg["sprite_px"])
        screen.blit(image, image.get_rect(center=self.to_screen(enemy["x"], enemy["y"], camera)))

    def draw_gem(self, screen, gem, camera):
        cfg = self.cfg["gem"]
        name = cfg["sprites"].get(str(gem["xp"]), cfg["sprites"]["1"])
        image = self.art.sprite(name, cfg["sprite_px"])
        screen.blit(image, image.get_rect(center=self.to_screen(gem["x"], gem["y"], camera)))

    def draw_spark(self, screen, spark, camera):
        cfg = self.cfg["spark_wand"]
        center = self.to_screen(spark["x"], spark["y"], camera)
        pygame.draw.circle(screen, color(cfg["color"]), center, cfg["radius_px"])

    def draw_blades(self, screen, camera):
        state = self.world["weapons"].get("spin_blades")
        if not state:
            return
        cfg = self.cfg["spin_blades"]
        image = self.art.sprite(cfg["sprite"], cfg["sprite_px"])
        hero = self.world["hero"]
        for x, y in state["positions"]:
            angle = math.atan2(y - hero["y"], x - hero["x"])
            # the sword picture points up, so turn it to point away from the hero
            turning = pygame.transform.rotate(image, -(math.degrees(angle) + 90))
            screen.blit(turning, turning.get_rect(center=self.to_screen(x, y, camera)))

    def draw_holy_ring(self, screen, camera):
        state = self.world["weapons"].get("holy_ring")
        if not state:
            return
        hero = self.world["hero"]
        ring = color(self.cfg["holy_ring"]["color"])
        ring.a = 90  # a faint circle, so you can see what it covers
        pygame.draw.circle(screen, ring, self.to_screen(hero["x"], hero["y"], camera),
                           int(state["radius_px"]), 2)

    def draw_hud(self, screen):
        hero = self.world["hero"]
        hud = self.cfg["hud"]
        text = color(hud["text_color"])
        size = hud["text_size_px"]
        hp_bar = pygame.Rect(hud["bar_x_px"], hud["bar_y_px"],
                             hud["bar_width_px"], hud["hp_bar_height_px"])
        pygame.draw.rect(screen, color(hud["hp_bar_back_color"]), hp_bar, border_radius=4)
        if hero["hp"] > 0:
            filled = pygame.Rect(hp_bar.x, hp_bar.y,
                                 int(hp_bar.width * hero["hp"] / hero["max_hp"]), hp_bar.height)
            pygame.draw.rect(screen, color(hud["hp_bar_color"]), filled, border_radius=4)
        xp_bar = pygame.Rect(hud["bar_x_px"], hp_bar.bottom + 2,
                             hud["bar_width_px"], hud["xp_bar_height_px"])
        pygame.draw.rect(screen, color(hud["xp_bar_back_color"]), xp_bar, border_radius=3)
        needed = rules.xp_for_next_level(self.world)
        if hero["xp"] > 0:
            filled = pygame.Rect(xp_bar.x, xp_bar.y,
                                 int(xp_bar.width * hero["xp"] / needed), xp_bar.height)
            pygame.draw.rect(screen, color(hud["xp_bar_color"]), filled, border_radius=3)
        screen.blit(self.label(size).render("HP {}".format(max(0, hero["hp"])), True, text),
                    (hud["bar_x_px"], xp_bar.bottom + 4))
        level = self.label(size).render("Lv {}".format(hero["level"]), True, text)
        screen.blit(level, (hud["bar_x_px"] + hp_bar.width + 8, hp_bar.y))
        timer = self.label(size).render(self.timer_text(), True, text)
        screen.blit(timer, (self.width - timer.get_width() - hud["bar_x_px"], hud["bar_y_px"]))
        owned = self.label(size).render(self.inventory_text(), True, text)
        screen.blit(owned, (hud["bar_x_px"], self.height - owned.get_height() - 8))

    def time_text(self):
        """How long the game has been running, like "0:45"."""
        return format_time(self.world["ticks"], self.cfg["ticks_per_second"])

    def timer_text(self):
        """How long you have survived and how long you have to last."""
        goal = rules.to_ticks(self.cfg, self.cfg["goal"]["victory_at_s"])
        return "{} / {}".format(self.time_text(),
                                format_time(goal, self.cfg["ticks_per_second"]))

    def inventory_text(self):
        """What you have, for example "Spark 2  Blades 1  Boots 1"."""
        parts = []
        for weapon_id, state in self.world["weapons"].items():
            parts.append("{} {}".format(self.cfg[weapon_id]["short"], state["level"]))
        for passive_id, level in self.world["passives"].items():
            parts.append("{} {}".format(self.cfg[passive_id]["short"], level))
        return "  ".join(parts)

    def card_rects(self):
        """Where the level-up cards are on the screen."""
        hud = self.cfg["hud"]
        count = len(self.world["offers"])
        height = hud["card_height_px"]
        total = count * height + (count - 1) * hud["card_gap_px"]
        top = (self.height - total) // 2
        margin = hud["card_side_margin_px"]
        return [pygame.Rect(margin, top + index * (height + hud["card_gap_px"]),
                            self.width - 2 * margin, height)
                for index in range(count)]

    def draw_cards(self, screen):
        hud = self.cfg["hud"]
        rects = self.card_rects()
        self.draw_shade(screen, 220)
        title = self.label(hud["line_size_px"] + 8).render("Level up!  Pick one", True,
                                                           color(hud["text_color"]))
        screen.blit(title, title.get_rect(center=(self.width // 2, rects[0].top - 30)))
        pointing_at = self.finger_px or self.mouse_px
        for index, (card, place) in enumerate(zip(self.world["offers"], rects)):
            edge = hud["card_edge_color_when_pointed"] if (pointing_at
                        and place.collidepoint(pointing_at)) else hud["card_edge_color"]
            pygame.draw.rect(screen, color(hud["card_color"]), place, border_radius=10)
            pygame.draw.rect(screen, color(edge), place, width=3, border_radius=10)
            self.draw_card_text(screen, card, place)

    def draw_card_text(self, screen, card, place):
        hud = self.cfg["hud"]
        text = color(hud["text_color"])
        name = self.label(hud["line_size_px"] + 8).render(card["name"], True, text)
        screen.blit(name, (place.x + 16, place.y + 14))
        if card["level"] is not None:
            level = self.label(hud["line_size_px"] + 4).render(
                "Lv {}".format(card["level"]), True, color(self.cfg["spark_wand"]["color"]))
            screen.blit(level, (place.right - level.get_width() - 16, place.y + 18))
        line = self.label(hud["text_size_px"]).render(card["text"], True, text)
        screen.blit(line, (place.x + 16, place.y + 58))
        hint = self.label(hud["text_size_px"] - 2).render("click or tap", True,
                                                          color(hud["card_edge_color"]))
        screen.blit(hint, (place.x + 16, place.bottom - hint.get_height() - 10))

    def draw_shade(self, screen, darkness):
        shade = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay = color(self.cfg["hud"]["overlay_color"])
        shade.fill((overlay.r, overlay.g, overlay.b, darkness))
        screen.blit(shade, (0, 0))

    def draw_banner(self, screen, title, lines):
        hud = self.cfg["hud"]
        self.draw_shade(screen, 205)
        text = color(hud["text_color"])
        middle = self.height // 2
        big = self.label(hud["title_size_px"]).render(title, True, text)
        screen.blit(big, big.get_rect(center=(self.width // 2, middle - 48)))
        for index, line in enumerate(lines):
            small = self.label(hud["line_size_px"]).render(line, True, text)
            screen.blit(small, small.get_rect(center=(self.width // 2, middle + 4 + index * 28)))

    def label(self, size):
        """Fonts are made once and reused."""
        if size not in self.fonts:
            self.fonts[size] = pygame.font.Font(None, size)
        return self.fonts[size]


async def main():
    cfg = rules.load_config(os.path.join("data", "game.json"))
    pygame.init()
    screen = pygame.display.set_mode((cfg["window"]["width_px"], cfg["window"]["height_px"]))
    pygame.display.set_caption(cfg["window"]["title"])
    clock = pygame.time.Clock()

    game = Game(cfg)
    step_seconds = rules.tick_seconds(cfg)
    accumulator = 0.0
    running = True

    while running:
        # real seconds since the last frame, never a huge jump after a stall
        accumulator += min(clock.tick(60) / 1000.0, 0.25)
        for event in pygame.event.get():
            if not game.handle(event):
                running = False
        while accumulator >= step_seconds:
            game.step_rules()
            accumulator -= step_seconds
        game.draw(screen)
        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
