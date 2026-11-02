"""The rules of Night Survivors.

No pygame and no drawing in this file. One call to step() moves the game
forward by exactly one tick (1/60 s), so the same code runs in a test, in a
window and in a web browser.

Every distance is in pixels and every short time is counted in ticks, so
nothing drifts. The numbers all come from data/game.json.
"""

import json
import math
import random

WEAPON_IDS = ("spark_wand", "spin_blades", "holy_ring")
PASSIVE_IDS = ("swift_boots", "big_heart", "magnet")


def load_config(path="data/game.json"):
    """Read every number of the game from data/game.json."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def tick_seconds(cfg):
    """How many seconds one tick is."""
    return 1.0 / cfg["ticks_per_second"]


def to_ticks(cfg, seconds):
    """0.8 seconds is 48 ticks."""
    return round(seconds * cfg["ticks_per_second"])


def new_world(cfg, rng=None):
    """Make a brand new game world. This is also how "play again" works."""
    hero_cfg = cfg["hero"]
    start = hero_cfg["start_weapon"]
    return {
        "cfg": cfg,
        "rng": rng or random.Random(),
        "state": "playing",  # "playing", "choosing", "game_over" or "victory"
        "paused": False,
        "ticks": 0,
        "time_s": 0.0,
        "kills": 0,
        "hero": {
            "x": 0.0,
            "y": 0.0,
            "hp": hero_cfg["max_hp"],
            "max_hp": hero_cfg["max_hp"],
            "xp": 0,
            "level": 1,
        },
        "enemies": [],
        "sparks": [],
        "gems": [],
        "weapons": {start: new_weapon_state(cfg, start, 1)},
        "passives": {},
        "offers": [],
        "levels_to_offer": 0,
        "spawn_ticks": 0,
        "bosses_out": [],  # which waves have already sent their boss
    }


# ---------- what the hero is worth right now ----------


def hero_speed(world):
    """Walking speed in pixels per second, with Swift Boots."""
    cfg = world["cfg"]
    level = world["passives"].get("swift_boots", 0)
    return cfg["hero"]["speed_px_per_s"] * (1 + cfg["swift_boots"]["speed_plus_per_level"] * level)


def magnet_radius(world):
    """How close a gem may be before it flies to the hero."""
    cfg = world["cfg"]
    level = world["passives"].get("magnet", 0)
    return cfg["hero"]["magnet_radius_px"] + cfg["magnet"]["magnet_plus_per_level_px"] * level


def xp_for_next_level(world):
    """5 XP for level 2, then 8, 11, 14, ..."""
    cfg = world["cfg"]["xp"]
    return cfg["first_level_xp"] + cfg["extra_xp_per_level"] * (world["hero"]["level"] - 1)


# ---------- the cards ----------


def choose_card(world, index):
    """The player picked one of the cards."""
    if world["state"] != "choosing" or not 0 <= index < len(world["offers"]):
        return
    chosen = world["offers"][index]
    if chosen["kind"] == "weapon":
        owned = world["weapons"].get(chosen["id"])
        if owned is None:
            world["weapons"][chosen["id"]] = new_weapon_state(world["cfg"], chosen["id"], chosen["level"])
        else:
            owned["level"] = chosen["level"]
    elif chosen["kind"] == "passive":
        _raise_passive(world, chosen["id"])
    else:  # nothing was left to offer
        _heal_hero(world, chosen["heal_hp"])
    world["levels_to_offer"] -= 1
    world["offers"] = make_offers(world) if world["levels_to_offer"] else []
    if not world["levels_to_offer"]:
        world["state"] = "playing"


def _raise_passive(world, passive_id):
    cfg = world["cfg"]
    level = world["passives"].get(passive_id, 0) + 1
    world["passives"][passive_id] = level
    if passive_id == "big_heart":
        hero = world["hero"]
        hero["max_hp"] += cfg["big_heart"]["max_hp_plus_per_level"]
        _heal_hero(world, cfg["big_heart"]["heal_per_level"])


def _heal_hero(world, points):
    hero = world["hero"]
    hero["hp"] = min(hero["max_hp"], hero["hp"] + points)


def _card_options(world):
    """Everything the player may be offered: never something at level 5."""
    cfg = world["cfg"]
    max_level = cfg["hero"]["max_item_level"]
    options = []
    for weapon_id in WEAPON_IDS:
        owned = world["weapons"].get(weapon_id)
        if owned is None:
            if len(world["weapons"]) < cfg["hero"]["max_weapons"]:
                options.append(card(world, "weapon", weapon_id, 1))
        elif owned["level"] < max_level:
            options.append(card(world, "weapon", weapon_id, owned["level"] + 1))
    for passive_id in PASSIVE_IDS:
        level = world["passives"].get(passive_id, 0)
        if level < max_level:
            options.append(card(world, "passive", passive_id, level + 1))
    return options


def make_offers(world):
    options = _card_options(world)
    if not options:
        return [card(world, "heal", None, world["cfg"]["xp"]["heal_when_nothing_left_hp"])]
    show = min(len(options), world["cfg"]["xp"]["cards_shown"])
    return world["rng"].sample(options, show)


def card(world, kind, item_id, level):
    """One card: what it is called, the level it gives and one line of text."""
    cfg = world["cfg"]
    if kind == "heal":
        return {"kind": "heal", "id": None, "level": None,
                "name": "Heal", "text": "Heal {} HP".format(level), "heal_hp": level}
    item_cfg = cfg[item_id]
    return {"kind": kind, "id": item_id, "level": level,
            "name": item_cfg["name"], "text": item_cfg["card_text"]}


# ---------- one tick ----------


def step(world, pointer):
    """Run one tick.

    pointer is the place the hero walks to, in world coordinates, or None when
    there is nothing to walk to.
    """
    if world["paused"] or world["state"] != "playing":
        return
    cfg = world["cfg"]
    dt = tick_seconds(cfg)
    world["ticks"] += 1
    world["time_s"] += dt
    _walk_hero(world, pointer, dt)
    _spawn_enemies(world)
    _move_enemies(world, dt)
    _use_weapons(world, dt)
    _move_sparks(world, dt)
    _move_gems(world, dt)
    if world["hero"]["hp"] <= 0:
        world["hero"]["hp"] = 0
        world["state"] = "game_over"
    elif world["ticks"] >= to_ticks(cfg, cfg["goal"]["victory_at_s"]):
        world["state"] = "victory"


def _walk_hero(world, pointer, dt):
    """Walk toward the pointer, but ignore it when it is very close."""
    if pointer is None:
        return
    cfg = world["cfg"]["hero"]
    hero = world["hero"]
    dx = pointer[0] - hero["x"]
    dy = pointer[1] - hero["y"]
    distance = math.hypot(dx, dy)
    if distance <= cfg["dead_zone_px"]:
        return
    # never walk past the dead zone
    step_length = min(hero_speed(world) * dt, distance - cfg["dead_zone_px"])
    hero["x"] += dx / distance * step_length
    hero["y"] += dy / distance * step_length


# ---------- enemies ----------


def wave_index(world):
    """Which line of the wave table the game is in right now."""
    cfg = world["cfg"]
    chosen = 0
    for index, wave in enumerate(cfg["waves"]):
        if world["ticks"] >= to_ticks(cfg, wave["from_s"]):
            chosen = index
    return chosen


def current_wave(world):
    """The line of the wave table the game is in: its enemy types and minimum."""
    return world["cfg"]["waves"][wave_index(world)]


def _spawn_enemies(world):
    """Once a second, top the number of alive enemies up to the minimum for this time."""
    cfg = world["cfg"]
    spawn = cfg["spawning"]
    world["spawn_ticks"] += 1
    if world["spawn_ticks"] < to_ticks(cfg, spawn["every_s"]):
        return
    world["spawn_ticks"] = 0
    index = wave_index(world)
    wave = cfg["waves"][index]
    _spawn_boss(world, index, wave)
    alive = len(world["enemies"])
    room_to_spawn = spawn["max_alive"] - alive
    wanted = wave["minimum_alive"] - alive
    limit = max(0, min(room_to_spawn, wanted, spawn["max_per_second"]))
    for _ in range(limit):
        kind = world["rng"].choice(wave["types"])
        world["enemies"].append(new_enemy(world, kind))


def _spawn_boss(world, wave_index, wave):
    """The boss of a wave comes once, and only that once."""
    kind = wave.get("boss")
    if kind is None or wave_index in world["bosses_out"]:
        return
    world["bosses_out"].append(wave_index)
    world["enemies"].append(new_enemy(world, kind))


def is_boss(world, kind):
    return bool(world["cfg"][kind].get("boss"))


def new_enemy(world, kind, x=None, y=None):
    """A new enemy on the circle just outside the screen, or where I asked."""
    enemy_cfg = world["cfg"][kind]
    if x is None or y is None:
        angle = world["rng"].uniform(0, 2 * math.pi)
        radius = world["cfg"]["spawning"]["circle_radius_px"]
        x = world["hero"]["x"] + math.cos(angle) * radius
        y = world["hero"]["y"] + math.sin(angle) * radius
    return {
        "kind": kind,
        "x": x,
        "y": y,
        "hp": enemy_cfg["hp"],
        "radius_px": enemy_cfg["radius_px"],
        "hurt_cooldown": 0,
        "blade_hits": {},
    }


def _move_enemies(world, dt):
    """Enemies fly at the hero. One that touches him hurts him at most once
    every hurts_every_s. A normal enemy that gets too far away is removed; the
    boss is never removed, it is only moved back next to the screen."""
    cfg = world["cfg"]
    spawn = cfg["spawning"]
    hero = world["hero"]
    alive = []
    for enemy in world["enemies"]:
        if enemy["hurt_cooldown"] > 0:
            enemy["hurt_cooldown"] -= 1
        dx = hero["x"] - enemy["x"]
        dy = hero["y"] - enemy["y"]
        distance = math.hypot(dx, dy)
        if is_boss(world, enemy["kind"]):
            if distance > spawn["boss_back_to_circle_px"]:
                # same direction, but back on the circle just outside the screen
                back = spawn["circle_radius_px"] / distance
                enemy["x"] = hero["x"] - dx * back
                enemy["y"] = hero["y"] - dy * back
                alive.append(enemy)
                continue
        elif distance > spawn["despawn_radius_px"]:
            continue  # too far away; new ones will come instead
        speed = cfg[enemy["kind"]]["speed_px_per_s"] * dt
        if distance > 0:
            enemy["x"] += dx / distance * speed
            enemy["y"] += dy / distance * speed
        if math.hypot(hero["x"] - enemy["x"], hero["y"] - enemy["y"]) <= cfg["hero"]["radius_px"] + enemy["radius_px"]:
            if enemy["hurt_cooldown"] <= 0:
                hero["hp"] -= cfg[enemy["kind"]]["damage"]
                enemy["hurt_cooldown"] = to_ticks(cfg, cfg["contact"]["hurts_every_s"])
        alive.append(enemy)
    world["enemies"] = alive


def _damage_enemy(world, enemy, damage):
    """Take health off an enemy; a dead one drops a gem with its XP."""
    enemy["hp"] -= damage
    if enemy["hp"] > 0:
        return
    world["enemies"].remove(enemy)
    world["kills"] += 1
    xp = world["cfg"][enemy["kind"]]["xp"]
    if xp > 0:  # the boss is worth nothing but fear
        world["gems"].append({"x": enemy["x"], "y": enemy["y"], "xp": xp})


# ---------- weapons ----------


def new_weapon_state(cfg, weapon_id, level):
    """The running bits a weapon needs: its cooldown, its angle, ..."""
    state = {"level": level}
    if weapon_id == "spark_wand":
        state["cooldown"] = _spark_wand_wait_ticks(cfg, level)
    elif weapon_id == "spin_blades":
        state["angle"] = 0.0
        state["positions"] = []
    elif weapon_id == "holy_ring":
        state["cooldown"] = to_ticks(cfg, cfg["holy_ring"]["hurts_every_s"])
        state["radius_px"] = cfg["holy_ring"]["radius_px"]
    return state


def _spark_wand_wait_ticks(cfg, level):
    """Each level of the wand shoots a little sooner than the last."""
    wand = cfg["spark_wand"]
    return to_ticks(cfg, wand["fire_every_s"]
                    - wand["fire_every_minus_per_level_s"] * (level - 1))


def _use_weapons(world, dt):
    for weapon_id, state in world["weapons"].items():
        if weapon_id == "spark_wand":
            _use_spark_wand(world, state)
        elif weapon_id == "spin_blades":
            _use_spin_blades(world, state, dt)
        elif weapon_id == "holy_ring":
            _use_holy_ring(world, state)


def _use_spark_wand(world, state):
    """Shoot at the nearest enemy by itself."""
    cfg = world["cfg"]["spark_wand"]
    level = state["level"]
    state["cooldown"] -= 1
    if state["cooldown"] > 0:
        return
    state["cooldown"] = _spark_wand_wait_ticks(world["cfg"], level)
    target = _nearest_enemy(world, world["hero"])
    if target is None:
        return
    hero = world["hero"]
    aim = math.atan2(target["y"] - hero["y"], target["x"] - hero["x"])
    count = cfg["sparks"] + sum(1 for level_at in cfg["extra_sparks_at_levels"] if level >= level_at)
    spread = math.radians(cfg["spread_deg"])
    damage = cfg["damage"] + cfg["damage_plus_per_level"] * (level - 1)
    for index in range(count):
        # with one spark this is exactly the aim angle
        angle = aim + (index - (count - 1) / 2) * spread
        world["sparks"].append({
            "x": hero["x"],
            "y": hero["y"],
            "vx": math.cos(angle) * cfg["speed_px_per_s"],
            "vy": math.sin(angle) * cfg["speed_px_per_s"],
            "ticks": 0,
            "damage": damage,
        })


def _use_spin_blades(world, state, dt):
    """Blades turn around the hero and cut what touches them."""
    cfg = world["cfg"]["spin_blades"]
    level = state["level"]
    count = cfg["blades"] + sum(1 for level_at in cfg["extra_blades_at_levels"] if level >= level_at)
    damage = cfg["damage"] + cfg["damage_plus_per_level"] * (level - 1)
    hits_every = to_ticks(world["cfg"], cfg["hits_every_s"])
    state["angle"] += 2 * math.pi * dt / cfg["turn_every_s"]
    hero = world["hero"]
    positions = []
    for index in range(count):
        angle = state["angle"] + index * 2 * math.pi / count
        x = hero["x"] + math.cos(angle) * cfg["orbit_radius_px"]
        y = hero["y"] + math.sin(angle) * cfg["orbit_radius_px"]
        positions.append((x, y))
        for enemy in list(world["enemies"]):
            if math.hypot(enemy["x"] - x, enemy["y"] - y) > enemy["radius_px"] + cfg["radius_px"]:
                continue
            last_hit = enemy["blade_hits"].get(index)
            if last_hit is not None and world["ticks"] - last_hit < hits_every:
                continue
            enemy["blade_hits"][index] = world["ticks"]
            _damage_enemy(world, enemy, damage)
    state["positions"] = positions


def _use_holy_ring(world, state):
    """Every half second the ring hurts everything inside it."""
    cfg = world["cfg"]["holy_ring"]
    level = state["level"]
    state["radius_px"] = cfg["radius_px"] + cfg["radius_plus_per_level_px"] * (level - 1)
    state["cooldown"] -= 1
    if state["cooldown"] > 0:
        return
    state["cooldown"] = to_ticks(world["cfg"], cfg["hurts_every_s"])
    damage = cfg["damage"] + cfg["damage_plus_per_level"] * (level - 1)
    hero = world["hero"]
    for enemy in list(world["enemies"]):
        if math.hypot(enemy["x"] - hero["x"], enemy["y"] - hero["y"]) <= state["radius_px"] + enemy["radius_px"]:
            _damage_enemy(world, enemy, damage)


def _nearest_enemy(world, point):
    best = None
    best_distance = None
    for enemy in world["enemies"]:
        distance = math.hypot(enemy["x"] - point["x"], enemy["y"] - point["y"])
        if best_distance is None or distance < best_distance:
            best = enemy
            best_distance = distance
    return best


def _move_sparks(world, dt):
    """A spark flies straight and breaks on the first enemy it touches."""
    cfg = world["cfg"]["spark_wand"]
    flying = []
    for spark in world["sparks"]:
        spark["x"] += spark["vx"] * dt
        spark["y"] += spark["vy"] * dt
        spark["ticks"] += 1
        if spark["ticks"] > to_ticks(world["cfg"], cfg["lifetime_s"]):
            continue  # it flew too far and vanished
        enemy = _enemies_touching(world, spark)
        if enemy is None:
            flying.append(spark)
        else:
            _damage_enemy(world, enemy, spark["damage"])
    world["sparks"] = flying


def _enemies_touching(world, spark):
    radius = world["cfg"]["spark_wand"]["radius_px"]
    for enemy in world["enemies"]:
        if math.hypot(enemy["x"] - spark["x"], enemy["y"] - spark["y"]) <= enemy["radius_px"] + radius:
            return enemy
    return None


# ---------- gems and levels ----------


def _move_gems(world, dt):
    """A gem inside the magnet radius flies to the hero and is picked up."""
    cfg = world["cfg"]
    hero = world["hero"]
    magnet = magnet_radius(world)
    picked_up = cfg["hero"]["radius_px"] + cfg["gem"]["radius_px"]
    left = []
    for gem in world["gems"]:
        dx = hero["x"] - gem["x"]
        dy = hero["y"] - gem["y"]
        distance = math.hypot(dx, dy)
        if distance <= magnet and distance > 0:
            speed = min(cfg["gem"]["fly_speed_px_per_s"] * dt, distance)
            gem["x"] += dx / distance * speed
            gem["y"] += dy / distance * speed
            distance = math.hypot(hero["x"] - gem["x"], hero["y"] - gem["y"])
        if distance <= picked_up:
            _gain_xp(world, gem["xp"])
            continue
        left.append(gem)
    world["gems"] = left


def _gain_xp(world, xp):
    """Add XP and open the cards for every level gained."""
    hero = world["hero"]
    hero["xp"] += xp
    while hero["xp"] >= xp_for_next_level(world):
        hero["xp"] -= xp_for_next_level(world)
        hero["level"] += 1
        world["levels_to_offer"] += 1
    if world["levels_to_offer"] and world["state"] == "playing":
        world["state"] = "choosing"
        world["offers"] = make_offers(world)
