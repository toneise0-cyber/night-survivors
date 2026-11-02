"""Tests for the rules in rules.py only: no drawing, no pygame.

Every number comes from data/game.json, so changing that file changes what
these tests expect.
"""

import copy
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import rules  # noqa: E402  (the path line above has to run first)

CFG = rules.load_config(os.path.join(ROOT, "data", "game.json"))
SPAWNS = CFG["spawning"]
WAVES = CFG["waves"]
GOAL = CFG["goal"]
WAND = CFG["spark_wand"]
BLADES = CFG["spin_blades"]
RING = CFG["holy_ring"]
BAT = CFG["bat"]
SLIME = CFG["slime"]
GHOST = CFG["ghost"]
DEMON = CFG["demon"]
HERO = CFG["hero"]
XP = CFG["xp"]
GEM = CFG["gem"]
BOOTS = CFG["swift_boots"]
HEART = CFG["big_heart"]
MAGNET = CFG["magnet"]

ENEMY_IDS = ("bat", "slime", "ghost", "demon")

# A test that kills a bat should not level up on the way.
NO_LEVEL_UP = ((("xp", "first_level_xp"), 10 ** 9),)
# A test about one rule should not be disturbed by dying.
NO_DAMAGE = [(("hero", "max_hp"), 10 ** 9)]
NO_DAMAGE += [(("{}".format(kind), "damage"), 0) for kind in ENEMY_IDS]
# Nothing at all comes by itself: one enemy, put by hand, is enough.
NO_SPAWNING = ((("waves",), [{"from_s": 0, "types": ["bat"], "minimum_alive": 0}]),)
FROZEN_BATS = ((("bat", "speed_px_per_s"), 0),)
FROZEN_EVERYONE = [(("{}".format(kind), "speed_px_per_s"), 0) for kind in ENEMY_IDS]


def world_with(overrides=(), seed=1):
    """A world made from the real numbers, with a few of them changed.

    An override is a path and a value: (("holy_ring", "radius_px"), 500) or,
    for a whole section, (("waves",), [...]).
    """
    cfg = copy.deepcopy(CFG)
    for path, value in overrides:
        place = cfg
        for key in path[:-1]:
            place = place[key]
        place[path[-1]] = value
    return rules.new_world(cfg, rng=random.Random(seed))


def quiet_world():
    """No bats appear by themselves, nobody dies and nobody levels up."""
    return world_with(list(NO_SPAWNING) + list(NO_DAMAGE) +
                      [(("spark_wand", "damage"), 0)] + list(NO_LEVEL_UP))


def wand_world():
    """Like quiet_world, but the wand works and bats stay where I put them."""
    return world_with(list(NO_SPAWNING) + list(NO_DAMAGE) + list(FROZEN_BATS) + list(NO_LEVEL_UP))


def spawn_world():
    """Only the spawner is interesting here: bats do not move and nothing dies."""
    return world_with([(("spark_wand", "damage"), 0)] + list(FROZEN_BATS) +
                      list(NO_DAMAGE) + list(NO_LEVEL_UP))


def still_world():
    """Like quiet_world, and the bats I place stay exactly where I put them."""
    return world_with(list(NO_SPAWNING) + list(NO_DAMAGE) + list(FROZEN_BATS) +
                      [(("spark_wand", "damage"), 0)] + list(NO_LEVEL_UP))


def kill_world(moves=False):
    """The wand really hurts and nothing comes by itself or dies.

    With moves=True the enemies I place walk at the hero; without it they stay
    exactly where I put them.
    """
    return world_with(list(NO_SPAWNING) + list(NO_DAMAGE) +
                      ([] if moves else FROZEN_EVERYONE) +
                      [(("hero", "magnet_radius_px"), 0)] + list(NO_LEVEL_UP))


def run(world, ticks, pointer=None):
    for _ in range(ticks):
        rules.step(world, pointer)


def ticks_for(world, seconds):
    return rules.to_ticks(world["cfg"], seconds)


def put_enemy(world, kind, x, y, hp=None):
    """Place one enemy by hand instead of waiting for the spawner."""
    enemy = rules.new_enemy(world, kind, x, y)
    if hp is not None:
        enemy["hp"] = hp
    world["enemies"].append(enemy)
    return enemy


def put_bat(world, x, y, hp=None):
    return put_enemy(world, "bat", x, y, hp)


def give_weapon(world, weapon_id, level):
    world["weapons"][weapon_id] = rules.new_weapon_state(world["cfg"], weapon_id, level)


def take_card(world, kind, item_id, level):
    """Choose a card the way the level-up screen does."""
    world["state"] = "choosing"
    world["levels_to_offer"] = 1
    world["offers"] = [rules.card(world, kind, item_id, level)]
    rules.choose_card(world, 0)


def give_xp(world, xp):
    """Drop a gem on the hero and pick it up: that is how XP really arrives."""
    world["gems"].append({"x": world["hero"]["x"], "y": world["hero"]["y"], "xp": xp})
    rules.step(world, None)


def distance(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


class TestSpawning(unittest.TestCase):
    def test_no_enemies_until_a_second_has_passed(self):
        world = spawn_world()
        run(world, ticks_for(world, SPAWNS["every_s"]) - 1)
        self.assertEqual(world["enemies"], [])

    def test_at_most_eight_enemies_appear_per_second(self):
        world = spawn_world()
        run(world, ticks_for(world, SPAWNS["every_s"]))
        self.assertEqual(len(world["enemies"]), SPAWNS["max_per_second"])

    def test_grows_to_the_minimum_and_stops_there(self):
        world = spawn_world()
        minimum = WAVES[0]["minimum_alive"]
        run(world, ticks_for(world, SPAWNS["every_s"] * 2))
        self.assertEqual(len(world["enemies"]), minimum)
        run(world, ticks_for(world, SPAWNS["every_s"] * 5))
        self.assertEqual(len(world["enemies"]), minimum)

    def test_enemies_arrive_on_the_circle_around_the_hero(self):
        world = spawn_world()
        run(world, ticks_for(world, SPAWNS["every_s"]))
        for enemy in world["enemies"]:
            self.assertAlmostEqual(distance(world["hero"], enemy),
                                   SPAWNS["circle_radius_px"], places=6)

    def test_enemies_come_from_every_side(self):
        world = spawn_world()
        run(world, ticks_for(world, SPAWNS["every_s"]))
        sides = {math.copysign(1, enemy["x"] - world["hero"]["x"]) for enemy in world["enemies"]}
        self.assertEqual(sides, {-1.0, 1.0})

    def test_only_the_types_of_the_current_wave_appear(self):
        world = world_with([(("waves",), [{"from_s": 0, "types": ["slime"], "minimum_alive": 30}]),
                            (("spark_wand", "damage"), 0)]
                           + FROZEN_EVERYONE + NO_DAMAGE + list(NO_LEVEL_UP))
        run(world, ticks_for(world, SPAWNS["every_s"] * 3))
        self.assertTrue(world["enemies"])
        for enemy in world["enemies"]:
            self.assertEqual(enemy["kind"], "slime")
            self.assertEqual(enemy["hp"], SLIME["hp"])

    def test_both_types_of_a_wave_can_appear(self):
        world = world_with([(("waves",), [{"from_s": 0, "types": ["bat", "ghost"],
                                           "minimum_alive": 60}]),
                            (("spark_wand", "damage"), 0)]
                           + FROZEN_EVERYONE + NO_DAMAGE + list(NO_LEVEL_UP))
        run(world, ticks_for(world, SPAWNS["every_s"] * 3))
        self.assertEqual({enemy["kind"] for enemy in world["enemies"]}, {"bat", "ghost"})

    def test_an_enemy_outside_the_despawn_radius_is_removed(self):
        world = spawn_world()
        put_bat(world, SPAWNS["despawn_radius_px"] + 1, 0.0)
        run(world, 1)
        self.assertEqual(world["enemies"], [])

    def test_an_enemy_inside_the_despawn_radius_stays(self):
        world = spawn_world()
        bat = put_bat(world, SPAWNS["despawn_radius_px"] - 1, 0.0)
        run(world, 1)
        self.assertIn(bat, world["enemies"])

    def test_the_cap_on_alive_enemies_is_respected(self):
        world = world_with([(("waves",), [{"from_s": 0, "types": ["bat"],
                                           "minimum_alive": SPAWNS["max_alive"] + 100}]),
                            (("spark_wand", "damage"), 0)]
                           + FROZEN_EVERYONE + NO_DAMAGE + list(NO_LEVEL_UP))
        run(world, ticks_for(world, SPAWNS["every_s"] * 20))
        self.assertEqual(len(world["enemies"]), SPAWNS["max_alive"])


class TestWaveTable(unittest.TestCase):
    """The lines of data/game.json change with time, so the game gets harder."""

    def real_table_world(self):
        # the real table, but nothing is stepped: only the tick number is moved
        return world_with(NO_DAMAGE + list(NO_LEVEL_UP))

    def test_the_wave_used_matches_the_time(self):
        world = self.real_table_world()
        for index, wave in enumerate(WAVES):
            world["ticks"] = ticks_for(world, wave["from_s"])
            self.assertEqual(rules.wave_index(world), index, str(wave))
            if index > 0:
                world["ticks"] -= 1
                self.assertEqual(rules.wave_index(world), index - 1)

    def test_the_wave_running_at_the_goal_time_is_the_last_one(self):
        world = self.real_table_world()
        world["ticks"] = rules.to_ticks(world["cfg"], GOAL["victory_at_s"])
        self.assertEqual(rules.current_wave(world), WAVES[-1])

    def test_the_minimum_alive_grows_along_the_table(self):
        minimum = [wave["minimum_alive"] for wave in WAVES]
        self.assertEqual(minimum, sorted(minimum))

    def test_the_boss_wave_is_the_only_one_with_a_boss(self):
        with_boss = [index for index, wave in enumerate(WAVES) if "boss" in wave]
        self.assertEqual(len(with_boss), 1)
        world = self.real_table_world()
        self.assertTrue(rules.is_boss(world, WAVES[with_boss[0]]["boss"]))
        self.assertFalse(rules.is_boss(world, "bat"))


class TestBoss(unittest.TestCase):
    def boss_world(self, moves=False):
        return world_with([(("waves",), [{"from_s": 0, "types": ["bat"],
                                          "minimum_alive": 0, "boss": "demon"}]),
                           (("hero", "magnet_radius_px"), 0)]
                          + ([] if moves else FROZEN_EVERYONE)
                          + NO_DAMAGE + list(NO_LEVEL_UP))

    def test_the_boss_appears_once_and_never_again(self):
        world = self.boss_world()
        run(world, ticks_for(world, SPAWNS["every_s"]))
        bosses = [enemy for enemy in world["enemies"] if enemy["kind"] == "demon"]
        self.assertEqual(len(bosses), 1)
        self.assertEqual(bosses[0]["hp"], DEMON["hp"])
        run(world, ticks_for(world, SPAWNS["every_s"] * 10))
        self.assertEqual([enemy for enemy in world["enemies"] if enemy["kind"] == "demon"],
                         bosses)

    def test_the_boss_is_never_removed_when_it_is_far_away(self):
        world = self.boss_world()
        boss = put_enemy(world, "demon", SPAWNS["despawn_radius_px"] + 50, 0.0)
        run(world, 1)
        self.assertIn(boss, world["enemies"])
        self.assertAlmostEqual(distance(world["hero"], boss),
                               SPAWNS["circle_radius_px"], places=6)

    def test_the_boss_walks_at_the_hero(self):
        world = self.boss_world(moves=True)
        boss = put_enemy(world, "demon", 500.0, 0.0)
        run(world, ticks_for(world, 1.0))
        self.assertAlmostEqual(boss["x"], 500.0 - DEMON["speed_px_per_s"], places=4)

    def test_the_boss_hurts_for_more_than_a_bat(self):
        world = world_with(list(NO_SPAWNING) + [(("spark_wand", "damage"), 0),
                                                (("hero", "max_hp"), 10 ** 9)])
        put_enemy(world, "demon", 0.0, 0.0)
        run(world, 1)
        self.assertEqual(world["hero"]["hp"], 10 ** 9 - DEMON["damage"])

    def test_a_dead_boss_gives_no_gem(self):
        world = self.boss_world()
        boss = put_enemy(world, "demon", 30.0, 0.0, hp=WAND["damage"])
        run(world, ticks_for(world, WAND["fire_every_s"] + 0.2))
        self.assertNotIn(boss, world["enemies"])
        self.assertEqual(world["kills"], 1)
        self.assertEqual(world["gems"], [])


class TestWalking(unittest.TestCase):
    def test_hero_walks_toward_the_pointer(self):
        world = quiet_world()
        run(world, ticks_for(world, 1.0), pointer=(300.0, 0.0))
        self.assertAlmostEqual(world["hero"]["x"], HERO["speed_px_per_s"], places=4)

    def test_hero_walks_diagonally(self):
        world = quiet_world()
        run(world, ticks_for(world, 1.0), pointer=(0.0, 300.0))
        self.assertAlmostEqual(world["hero"]["x"], 0.0, places=6)
        self.assertAlmostEqual(world["hero"]["y"], HERO["speed_px_per_s"], places=4)

    def test_hero_stops_at_the_dead_zone(self):
        world = quiet_world()
        run(world, ticks_for(world, 5.0), pointer=(20.0, 0.0))
        self.assertAlmostEqual(world["hero"]["x"], 20.0 - HERO["dead_zone_px"], places=6)

    def test_hero_stands_still_without_a_pointer(self):
        world = quiet_world()
        run(world, ticks_for(world, 5.0))
        self.assertEqual((world["hero"]["x"], world["hero"]["y"]), (0.0, 0.0))


class TestDamage(unittest.TestCase):
    def test_bats_fly_at_the_hero(self):
        world = quiet_world()
        put_bat(world, 200.0, 0.0)
        run(world, ticks_for(world, 1.0))
        self.assertAlmostEqual(world["enemies"][0]["x"], 200.0 - BAT["speed_px_per_s"], places=4)

    def test_a_touching_bat_hurts_once_every_half_second(self):
        world = world_with(list(NO_SPAWNING) + [(("spark_wand", "damage"), 0)] + list(NO_LEVEL_UP))
        put_bat(world, 0.0, 0.0)
        start = world["hero"]["max_hp"]
        half = ticks_for(world, CFG["contact"]["hurts_every_s"])
        run(world, half)
        self.assertEqual(world["hero"]["hp"], start - BAT["damage"])
        run(world, half)
        self.assertEqual(world["hero"]["hp"], start - 2 * BAT["damage"])

    def test_two_bats_hurt_twice(self):
        world = world_with(list(NO_SPAWNING) + [(("spark_wand", "damage"), 0)] + list(NO_LEVEL_UP))
        put_bat(world, 0.0, 0.0)
        put_bat(world, 0.0, 0.0)
        run(world, 1)
        self.assertEqual(world["hero"]["hp"], world["hero"]["max_hp"] - 2 * BAT["damage"])

    def test_hp_never_goes_below_zero_and_the_game_is_over(self):
        world = world_with(list(NO_SPAWNING) + [(("spark_wand", "damage"), 0),
                                                (("hero", "max_hp"), BAT["damage"])])
        put_bat(world, 0.0, 0.0)
        run(world, 1)
        self.assertEqual(world["hero"]["hp"], 0)
        self.assertEqual(world["state"], "game_over")

    def test_a_finished_world_does_not_move_anymore(self):
        world = world_with(list(NO_SPAWNING) + [(("spark_wand", "damage"), 0),
                                                (("hero", "max_hp"), BAT["damage"])])
        put_bat(world, 100.0, 0.0)  # reaches the hero after about one second
        run(world, ticks_for(world, 10.0))
        self.assertEqual(world["state"], "game_over")
        frozen = (world["hero"]["x"], world["enemies"][0]["x"], world["time_s"], world["ticks"])
        run(world, ticks_for(world, 5.0), pointer=(500.0, 500.0))
        self.assertEqual((world["hero"]["x"], world["enemies"][0]["x"],
                          world["time_s"], world["ticks"]), frozen)

    def test_paused_world_does_nothing(self):
        world = spawn_world()
        world["paused"] = True
        run(world, ticks_for(world, 5.0), pointer=(200.0, 0.0))
        self.assertEqual(world["enemies"], [])
        self.assertEqual(world["hero"]["x"], 0.0)
        self.assertEqual(world["time_s"], 0.0)

    def test_play_again_starts_a_clean_world(self):
        world = spawn_world()
        run(world, ticks_for(world, 4.0), pointer=(100.0, 0.0))
        self.assertTrue(world["enemies"])
        again = rules.new_world(world["cfg"], rng=random.Random(1))
        self.assertEqual(again["enemies"], [])
        self.assertEqual(again["kills"], 0)
        self.assertEqual(again["gems"], [])
        self.assertEqual(again["state"], "playing")
        self.assertEqual(again["hero"]["level"], 1)


class TestSparkWand(unittest.TestCase):
    def test_the_wand_shoots_by_itself_at_the_nearest_bat(self):
        world = wand_world()
        near = put_bat(world, 40.0, 0.0)
        put_bat(world, 0.0, 120.0)
        run(world, ticks_for(world, WAND["fire_every_s"]))
        self.assertEqual(len(world["sparks"]), WAND["sparks"])
        self.assertGreater(world["sparks"][0]["vx"], 0)
        run(world, ticks_for(world, 1.0))
        self.assertNotIn(near, world["enemies"])
        self.assertEqual(world["kills"], 1)

    def test_a_spark_breaks_on_the_first_bat(self):
        world = wand_world()
        first = put_bat(world, 30.0, 0.0, hp=BAT["hp"] + WAND["damage"] + 1)
        second = put_bat(world, 60.0, 0.0)
        run(world, ticks_for(world, WAND["fire_every_s"] * 1.5))
        self.assertEqual(first["hp"], BAT["hp"] + 1)
        self.assertEqual(second["hp"], BAT["hp"])

    def test_a_spark_that_hits_nothing_disappears(self):
        world = wand_world()
        put_bat(world, 40.0, 0.0)
        run(world, ticks_for(world, WAND["fire_every_s"]))
        world["enemies"] = []  # the bat is gone, the spark keeps flying
        run(world, ticks_for(world, WAND["lifetime_s"]) + 1)
        self.assertEqual(world["sparks"], [])

    def test_an_empty_world_gets_no_sparks(self):
        world = wand_world()
        run(world, ticks_for(world, 10.0))
        self.assertEqual(world["sparks"], [])

    def test_the_next_shot_comes_only_after_the_wait(self):
        world = wand_world()
        put_bat(world, SPAWNS["despawn_radius_px"] - 10, 0.0)  # out of reach
        run(world, ticks_for(world, WAND["fire_every_s"]) - 1)
        self.assertEqual(world["sparks"], [])
        run(world, 1)
        self.assertEqual(len(world["sparks"]), WAND["sparks"])

    def test_a_level_2_wand_hits_harder(self):
        world = wand_world()
        give_weapon(world, "spark_wand", 2)
        bat = put_bat(world, 30.0, 0.0, hp=10 ** 6)
        run(world, ticks_for(world, WAND["fire_every_s"]) + 5)
        self.assertEqual(bat["hp"], 10 ** 6 - WAND["damage"] - WAND["damage_plus_per_level"])

    def test_a_level_2_wand_shoots_again_sooner(self):
        world = wand_world()
        give_weapon(world, "spark_wand", 2)
        put_bat(world, SPAWNS["despawn_radius_px"] - 10, 0.0, hp=10 ** 6)  # out of reach
        faster = WAND["fire_every_s"] - WAND["fire_every_minus_per_level_s"]
        run(world, ticks_for(world, faster))
        self.assertEqual(len(world["sparks"]), WAND["sparks"])
        run(world, ticks_for(world, faster))
        self.assertEqual(len(world["sparks"]), 2 * WAND["sparks"],
                         "at level 1 the second shot would still be on its way")

    def test_the_wand_shoots_more_sparks_at_levels_3_and_5(self):
        for level, expected in ((1, WAND["sparks"]), (3, WAND["sparks"] + 1),
                                (5, WAND["sparks"] + 2)):
            world = wand_world()
            give_weapon(world, "spark_wand", level)
            put_bat(world, SPAWNS["despawn_radius_px"] - 10, 0.0, hp=10 ** 6)  # out of reach
            run(world, ticks_for(world, WAND["fire_every_s"]))
            self.assertEqual(len(world["sparks"]), expected, "level {}".format(level))


class TestGems(unittest.TestCase):
    def test_a_dead_bat_drops_a_gem_with_its_xp(self):
        world = world_with(list(NO_SPAWNING) + list(FROZEN_BATS) + list(NO_DAMAGE) +
                           [(("hero", "magnet_radius_px"), 0)] + list(NO_LEVEL_UP))
        put_bat(world, 40.0, 0.0)
        run(world, ticks_for(world, 1.0))
        self.assertEqual(len(world["gems"]), 1)
        self.assertEqual(world["gems"][0]["xp"], BAT["xp"])
        self.assertAlmostEqual(world["gems"][0]["x"], 40.0, places=4)

    def test_a_gem_inside_the_magnet_radius_flys_to_the_hero(self):
        world = quiet_world()
        gem = {"x": 50.0, "y": 0.0, "xp": BAT["xp"]}
        world["gems"].append(gem)
        run(world, 1)
        self.assertAlmostEqual(gem["x"],
                               50.0 - GEM["fly_speed_px_per_s"] / CFG["ticks_per_second"], places=4)

    def test_a_gem_outside_the_magnet_radius_stays_where_it_is(self):
        world = quiet_world()
        far = HERO["magnet_radius_px"] + 20
        gem = {"x": float(far), "y": 0.0, "xp": BAT["xp"]}
        world["gems"].append(gem)
        run(world, 10)
        self.assertEqual((gem["x"], gem["y"]), (float(far), 0.0))

    def test_a_gem_that_reaches_the_hero_gives_him_xp(self):
        world = quiet_world()
        world["gems"].append({"x": 20.0, "y": 0.0, "xp": BAT["xp"]})
        run(world, ticks_for(world, 1.0))
        self.assertEqual(world["gems"], [])
        self.assertEqual(world["hero"]["xp"], BAT["xp"])

    def test_a_magnet_pulls_gems_from_farther_away(self):
        world = quiet_world()
        take_card(world, "passive", "magnet", 1)
        far = HERO["magnet_radius_px"] + MAGNET["magnet_plus_per_level_px"] - 10
        world["gems"].append({"x": float(far), "y": 0.0, "xp": BAT["xp"]})
        run(world, 1)
        self.assertLess(world["gems"][0]["x"], far)


class TestLevelsAndCards(unittest.TestCase):
    def test_the_xp_needed_grows_by_three_each_level(self):
        world = world_with(list(NO_SPAWNING))
        self.assertEqual(rules.xp_for_next_level(world), XP["first_level_xp"])
        give_xp(world, XP["first_level_xp"])
        rules.choose_card(world, 0)
        self.assertEqual(rules.xp_for_next_level(world),
                         XP["first_level_xp"] + XP["extra_xp_per_level"])
        give_xp(world, XP["first_level_xp"] + XP["extra_xp_per_level"])
        rules.choose_card(world, 0)
        self.assertEqual(world["hero"]["level"], 3)
        self.assertEqual(rules.xp_for_next_level(world),
                         XP["first_level_xp"] + 2 * XP["extra_xp_per_level"])

    def test_a_full_xp_bar_levels_up_and_shows_three_cards(self):
        world = world_with(list(NO_SPAWNING))
        give_xp(world, XP["first_level_xp"])
        self.assertEqual(world["hero"]["level"], 2)
        self.assertEqual(world["state"], "choosing")
        self.assertEqual(len(world["offers"]), XP["cards_shown"])

    def test_the_game_waits_while_you_choose(self):
        world = world_with(list(NO_SPAWNING))
        give_xp(world, XP["first_level_xp"])
        before = (world["time_s"], world["ticks"])
        run(world, 60, pointer=(300.0, 0.0))
        self.assertEqual((world["time_s"], world["ticks"]), before)
        self.assertEqual(world["hero"]["x"], 0.0)

    def test_a_card_for_a_weapon_you_do_not_have_adds_it(self):
        world = world_with(list(NO_SPAWNING))
        take_card(world, "weapon", "spin_blades", 1)
        self.assertEqual(world["weapons"]["spin_blades"]["level"], 1)
        self.assertEqual(world["state"], "playing")

    def test_a_card_for_a_weapon_you_have_raises_its_level(self):
        world = world_with(list(NO_SPAWNING))
        take_card(world, "weapon", "spark_wand", 2)
        self.assertEqual(world["weapons"]["spark_wand"]["level"], 2)

    def test_a_card_chooses_only_once(self):
        world = world_with(list(NO_SPAWNING))
        take_card(world, "weapon", "spin_blades", 1)
        rules.choose_card(world, 0)  # already taken: nothing happens
        self.assertEqual(world["weapons"]["spin_blades"]["level"], 1)
        self.assertEqual(world["state"], "playing")

    def test_a_big_gem_can_give_two_levels_and_you_choose_twice(self):
        world = world_with(list(NO_SPAWNING))
        needed = XP["first_level_xp"] + XP["first_level_xp"] + XP["extra_xp_per_level"]
        give_xp(world, needed)
        self.assertEqual(world["hero"]["level"], 3)
        self.assertEqual(world["levels_to_offer"], 2)
        rules.choose_card(world, 0)
        self.assertEqual(world["state"], "choosing")
        self.assertEqual(len(world["offers"]), XP["cards_shown"])
        rules.choose_card(world, 0)
        self.assertEqual(world["state"], "playing")
        self.assertEqual(world["offers"], [])

    def test_a_new_weapon_is_not_offered_once_you_have_three(self):
        world = world_with(list(NO_SPAWNING))
        for weapon_id in rules.WEAPON_IDS:
            give_weapon(world, weapon_id, 1)
        for _ in range(20):
            for offer in rules.make_offers(world):
                if offer["kind"] == "weapon":
                    self.assertIn(offer["id"], world["weapons"],
                                  "no brand new weapon while you already have three")

    def test_nothing_is_ever_offered_above_the_top_level(self):
        world = world_with(list(NO_SPAWNING))
        for weapon_id in rules.WEAPON_IDS:
            give_weapon(world, weapon_id, HERO["max_item_level"])
        for passive_id in rules.PASSIVE_IDS:
            world["passives"][passive_id] = HERO["max_item_level"] - 1
        for _ in range(20):
            for offer in rules.make_offers(world):
                self.assertLessEqual(offer["level"] or 1, HERO["max_item_level"])
                self.assertNotIn(offer["id"], rules.WEAPON_IDS, "a maxed weapon is not offered")

    def test_when_nothing_is_left_the_card_heals(self):
        world = world_with(list(NO_SPAWNING))
        for weapon_id in rules.WEAPON_IDS:
            give_weapon(world, weapon_id, HERO["max_item_level"])
        for passive_id in rules.PASSIVE_IDS:
            world["passives"][passive_id] = HERO["max_item_level"]
        world["hero"]["hp"] = 10
        offers = rules.make_offers(world)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["kind"], "heal")
        world["offers"] = offers
        world["state"] = "choosing"
        world["levels_to_offer"] = 1
        rules.choose_card(world, 0)
        self.assertEqual(world["hero"]["hp"], 10 + XP["heal_when_nothing_left_hp"])
        self.assertEqual(world["state"], "playing")

    def test_swift_boots_make_the_hero_walk_faster(self):
        world = world_with(list(NO_SPAWNING) + list(NO_DAMAGE) + list(NO_LEVEL_UP))
        take_card(world, "passive", "swift_boots", 1)
        run(world, ticks_for(world, 1.0), pointer=(500.0, 0.0))
        expected = HERO["speed_px_per_s"] * (1 + BOOTS["speed_plus_per_level"])
        self.assertAlmostEqual(world["hero"]["x"], expected, places=3)

    def test_big_heart_gives_more_hp_and_heals(self):
        world = world_with(list(NO_SPAWNING))
        world["hero"]["hp"] = 50
        take_card(world, "passive", "big_heart", 1)
        self.assertEqual(world["hero"]["max_hp"], HERO["max_hp"] + HEART["max_hp_plus_per_level"])
        self.assertEqual(world["hero"]["hp"], 50 + HEART["heal_per_level"])

    def test_big_heart_never_heals_above_the_maximum(self):
        world = world_with(list(NO_SPAWNING))
        take_card(world, "passive", "big_heart", 1)
        self.assertEqual(world["hero"]["hp"], world["hero"]["max_hp"])


class TestSpinBlades(unittest.TestCase):
    def test_a_blade_cuts_an_enemy_it_touches(self):
        world = quiet_world()
        give_weapon(world, "spin_blades", 1)
        bat = put_bat(world, BLADES["orbit_radius_px"], 0.0, hp=10 ** 6)
        run(world, 1)
        self.assertEqual(bat["hp"], 10 ** 6 - BLADES["damage"])

    def test_a_blade_cuts_the_same_enemy_only_every_half_second(self):
        world = world_with(list(NO_SPAWNING) + list(NO_DAMAGE) + list(FROZEN_BATS) +
                           [(("spark_wand", "damage"), 0),
                            (("spin_blades", "blades"), 1),
                            (("spin_blades", "extra_blades_at_levels"), []),
                            (("spin_blades", "turn_every_s"), 10 ** 6)] + list(NO_LEVEL_UP))
        give_weapon(world, "spin_blades", 1)
        bat = put_bat(world, BLADES["orbit_radius_px"], 0.0, hp=10 ** 9)
        half = ticks_for(world, CFG["contact"]["hurts_every_s"])
        run(world, half)
        self.assertEqual(bat["hp"], 10 ** 9 - BLADES["damage"])
        run(world, half)
        self.assertEqual(bat["hp"], 10 ** 9 - 2 * BLADES["damage"])

    def test_blades_are_added_at_levels_2_and_4(self):
        world = quiet_world()
        for level, expected in ((1, BLADES["blades"]), (2, BLADES["blades"] + 1),
                                (3, BLADES["blades"] + 1), (4, BLADES["blades"] + 2)):
            give_weapon(world, "spin_blades", level)
            run(world, 1)
            self.assertEqual(len(world["weapons"]["spin_blades"]["positions"]), expected)

    def test_blades_stay_at_the_orbit_distance(self):
        world = quiet_world()
        give_weapon(world, "spin_blades", 1)
        run(world, 30)
        for x, y in world["weapons"]["spin_blades"]["positions"]:
            self.assertAlmostEqual(distance({"x": x, "y": y}, world["hero"]),
                                   BLADES["orbit_radius_px"], places=6)

    def test_blade_damage_grows_with_the_level(self):
        world = quiet_world()
        give_weapon(world, "spin_blades", 2)
        bat = put_bat(world, BLADES["orbit_radius_px"], 0.0, hp=10 ** 6)
        run(world, 1)
        self.assertEqual(bat["hp"], 10 ** 6 - BLADES["damage"] - BLADES["damage_plus_per_level"])


class TestHolyRing(unittest.TestCase):
    def test_the_ring_hurts_everything_inside_it(self):
        world = still_world()
        give_weapon(world, "holy_ring", 1)
        inside = [put_bat(world, 30.0, 0.0, hp=10 ** 6), put_bat(world, 0.0, -20.0, hp=10 ** 6)]
        run(world, ticks_for(world, RING["hurts_every_s"]))
        for bat in inside:
            self.assertEqual(bat["hp"], 10 ** 6 - RING["damage"])

    def test_the_ring_does_not_hurt_anything_outside_it(self):
        world = still_world()
        give_weapon(world, "holy_ring", 1)
        far = put_bat(world, RING["radius_px"] + BAT["radius_px"] + 10, 0.0, hp=10 ** 6)
        run(world, ticks_for(world, RING["hurts_every_s"] * 2))
        self.assertEqual(far["hp"], 10 ** 6)

    def test_the_ring_grows_and_hits_harder_with_each_level(self):
        world = still_world()
        give_weapon(world, "holy_ring", 2)
        bat = put_bat(world, RING["radius_px"] + 5, 0.0, hp=10 ** 6)
        run(world, ticks_for(world, RING["hurts_every_s"]))
        self.assertEqual(bat["hp"], 10 ** 6 - RING["damage"] - RING["damage_plus_per_level"])
        self.assertEqual(world["weapons"]["holy_ring"]["radius_px"],
                         RING["radius_px"] + RING["radius_plus_per_level_px"])


class TestEnemyTypes(unittest.TestCase):
    def test_one_wand_shot_kills_a_bat(self):
        world = kill_world()
        bat = put_enemy(world, "bat", 30.0, 0.0)
        run(world, ticks_for(world, WAND["fire_every_s"]) + 5)
        self.assertNotIn(bat, world["enemies"])

    def test_one_wand_shot_does_not_kill_a_slime(self):
        self.assertGreater(SLIME["hp"], BAT["hp"])
        world = kill_world()
        slime = put_enemy(world, "slime", 30.0, 0.0)
        run(world, ticks_for(world, WAND["fire_every_s"]) + 5)
        self.assertEqual(slime["hp"], SLIME["hp"] - WAND["damage"])

    def test_a_slime_drops_a_gem_worth_two_xp(self):
        world = kill_world()
        put_enemy(world, "slime", 30.0, 0.0, hp=WAND["damage"])
        run(world, ticks_for(world, WAND["fire_every_s"]) + 5)
        self.assertEqual([gem["xp"] for gem in world["gems"]], [2])

    def test_a_ghost_is_faster_than_the_hero(self):
        self.assertGreater(GHOST["speed_px_per_s"], HERO["speed_px_per_s"])
        world = kill_world(moves=True)
        ghost = put_enemy(world, "ghost", 300.0, 0.0)
        run(world, ticks_for(world, 1.0))
        self.assertAlmostEqual(ghost["x"], 300.0 - GHOST["speed_px_per_s"], places=4)

    def test_a_ghost_hurts_the_hero_for_its_own_damage(self):
        world = world_with(list(NO_SPAWNING) + [(("spark_wand", "damage"), 0),
                                                (("hero", "max_hp"), 10 ** 9)])
        put_enemy(world, "ghost", 0.0, 0.0)
        run(world, 1)
        self.assertEqual(world["hero"]["hp"], 10 ** 9 - GHOST["damage"])


class TestWinning(unittest.TestCase):
    def test_you_win_when_the_time_is_up(self):
        world = kill_world()
        run(world, ticks_for(world, GOAL["victory_at_s"]) - 1)
        self.assertEqual(world["state"], "playing")
        run(world, 1)
        self.assertEqual(world["state"], "victory")

    def test_a_won_game_does_not_move_anymore(self):
        world = kill_world()
        run(world, ticks_for(world, GOAL["victory_at_s"]))
        frozen = (world["hero"]["x"], world["time_s"], world["ticks"], world["kills"])
        run(world, 60, pointer=(500.0, 500.0))
        self.assertEqual((world["hero"]["x"], world["time_s"],
                          world["ticks"], world["kills"]), frozen)

    def test_a_hero_without_hp_still_loses_first(self):
        world = world_with(list(NO_SPAWNING) + [(("hero", "max_hp"), BAT["damage"]),
                                                (("spark_wand", "damage"), 0),
                                                (("goal", "victory_at_s"), 0.0)]
                           + list(NO_LEVEL_UP))
        put_bat(world, 0.0, 0.0)
        run(world, 1)
        self.assertEqual(world["state"], "game_over")

    def test_a_brand_new_world_has_no_boss_out_yet(self):
        self.assertEqual(rules.new_world(CFG)["bosses_out"], [])


if __name__ == "__main__":
    unittest.main()
