"""Regras da fila de reprodução (domain/play_queue.py)."""

import random
import unittest

from ytdown.domain.play_queue import RESTART_THRESHOLD_MS, PlayQueue, RepeatMode

SONGS = ["a", "b", "c", "d", "e"]


def queue(items=SONGS, start=0, seed=7, shuffle=False, repeat=RepeatMode.OFF) -> PlayQueue:
    q = PlayQueue(random.Random(seed))
    q.repeat = repeat
    q.shuffle = shuffle
    q.replace(items, start)
    return q


def play_until_the_end(q: PlayQueue, limit=100) -> list:
    """Os itens que tocam, a partir do atual, até a fila acabar (faixas terminando sozinhas)."""
    played = [q.current]
    while (item := q.next()) is not None and len(played) < limit:
        played.append(item)
    return played


class BasicTests(unittest.TestCase):
    def test_empty_queue(self):
        q = PlayQueue()
        self.assertEqual((len(q), q.current, q.current_index, q.upcoming()), (0, None, None, []))
        self.assertIsNone(q.next())
        self.assertIsNone(q.next(manual=True))
        self.assertIsNone(q.previous(0))
        self.assertIsNone(q.replace([]))

    def test_replace_starts_at_the_chosen_item(self):
        q = queue(start=2)
        self.assertEqual((q.items, q.current, q.current_index), (SONGS, "c", 2))
        self.assertEqual(q.upcoming(), ["d", "e"])

    def test_replace_with_an_invalid_start(self):
        with self.assertRaises(IndexError):
            queue(start=5)

    def test_plays_in_order_and_stops_at_the_end(self):
        q = queue()
        self.assertEqual(play_until_the_end(q), SONGS)
        self.assertIsNone(q.current)

    def test_after_stopping_at_the_end_play_starts_over(self):
        q = queue(start=4)
        self.assertIsNone(q.next())
        self.assertEqual(q.next(), "a")

    def test_the_same_song_can_be_in_the_queue_twice(self):
        q = queue(["a", "b", "a"])
        self.assertEqual(play_until_the_end(q), ["a", "b", "a"])

    def test_select_jumps_to_an_item(self):
        q = queue()
        self.assertEqual(q.select(3), "d")
        self.assertEqual(q.next(), "e")

    def test_clear(self):
        q = queue()
        q.clear()
        self.assertEqual((len(q), q.current), (0, None))
        self.assertIsNone(q.next())


class EditTests(unittest.TestCase):
    def test_append_goes_to_the_end(self):
        q = queue(["a", "b"])
        q.append(["c", "d"])
        self.assertEqual(q.items, ["a", "b", "c", "d"])
        self.assertEqual(play_until_the_end(q), ["a", "b", "c", "d"])

    def test_play_next_goes_right_after_the_current_one_in_the_given_order(self):
        q = queue(start=1)
        q.play_next(["x", "y"])
        self.assertEqual(q.items, ["a", "b", "x", "y", "c", "d", "e"])
        self.assertEqual(q.upcoming()[:2], ["x", "y"])

    def test_play_next_with_nothing_playing_goes_first(self):
        q = queue(start=4)
        q.next()  # Fim da fila: nada tocando.
        q.play_next(["x"])
        self.assertEqual(q.next(), "x")

    def test_removing_another_item(self):
        q = queue(start=2)
        self.assertFalse(q.remove(0))
        self.assertEqual((q.current, q.current_index, q.items), ("c", 1, ["b", "c", "d", "e"]))
        self.assertFalse(q.remove(2))  # "d"
        self.assertEqual(q.next(), "e")

    def test_removing_the_current_item_moves_to_the_following_one(self):
        q = queue(start=1)
        self.assertTrue(q.remove(1))
        self.assertEqual((q.current, q.items), ("c", ["a", "c", "d", "e"]))

    def test_removing_the_current_last_item_ends_the_queue(self):
        q = queue(start=4)
        self.assertTrue(q.remove(4))
        self.assertIsNone(q.current)

    def test_removing_the_current_last_item_with_repeat_all_wraps(self):
        q = queue(start=4, repeat=RepeatMode.ALL)
        self.assertTrue(q.remove(4))
        self.assertEqual(q.current, "a")

    def test_removing_the_only_item(self):
        q = queue(["a"], repeat=RepeatMode.ALL)
        self.assertTrue(q.remove(0))
        self.assertEqual((q.current, len(q)), (None, 0))

    def test_move_changes_what_plays_next(self):
        q = queue(start=0)
        q.move(4, 1)  # "e" logo depois de "a".
        self.assertEqual(q.items, ["a", "e", "b", "c", "d"])
        self.assertEqual(q.current, "a")
        self.assertEqual(play_until_the_end(q), ["a", "e", "b", "c", "d"])

    def test_moving_the_current_item_keeps_it_current(self):
        q = queue(start=0)
        q.move(0, 3)
        self.assertEqual((q.current, q.current_index), ("a", 3))
        self.assertEqual(q.upcoming(), ["e"])


class RepeatTests(unittest.TestCase):
    def test_repeat_all_starts_over_at_the_end(self):
        q = queue(start=4, repeat=RepeatMode.ALL)
        self.assertEqual([q.next() for _ in range(3)], ["a", "b", "c"])

    def test_repeat_one_plays_the_same_song_when_it_ends(self):
        q = queue(start=2, repeat=RepeatMode.ONE)
        self.assertEqual([q.next() for _ in range(3)], ["c", "c", "c"])

    def test_with_repeat_one_the_next_button_still_changes_song_and_wraps(self):
        q = queue(start=3, repeat=RepeatMode.ONE)
        self.assertEqual([q.next(manual=True) for _ in range(3)], ["e", "a", "b"])

    def test_next_button_stops_at_the_end_without_repeat(self):
        q = queue(start=4)
        self.assertIsNone(q.next(manual=True))

    def test_repeat_button_cycles(self):
        q = PlayQueue()
        self.assertEqual([q.cycle_repeat() for _ in range(3)], [RepeatMode.ALL, RepeatMode.ONE, RepeatMode.OFF])


class PreviousTests(unittest.TestCase):
    def test_after_three_seconds_previous_restarts_the_song(self):
        q = queue(start=2)
        self.assertEqual(q.previous(RESTART_THRESHOLD_MS + 1), "c")
        self.assertEqual(q.current, "c")

    def test_in_the_first_three_seconds_previous_goes_back(self):
        q = queue(start=2)
        self.assertEqual(q.previous(RESTART_THRESHOLD_MS), "b")
        self.assertEqual(q.previous(0), "a")

    def test_previous_on_the_first_song_restarts_it(self):
        q = queue(start=0)
        self.assertEqual(q.previous(0), "a")

    def test_previous_on_the_first_song_with_repeat_goes_to_the_last(self):
        q = queue(start=0, repeat=RepeatMode.ALL)
        self.assertEqual(q.previous(0), "e")

    def test_previous_with_nothing_playing(self):
        q = queue(start=4)
        q.next()
        self.assertIsNone(q.previous(0))


class ShuffleTests(unittest.TestCase):
    ITEMS = list(range(20))

    def test_turning_shuffle_on_keeps_the_current_song_and_shuffles_the_rest(self):
        q = queue(self.ITEMS, start=5)
        q.shuffle = True
        self.assertEqual(q.current, 5)
        upcoming = q.upcoming()
        self.assertEqual(sorted(upcoming), [i for i in self.ITEMS if i != 5])
        self.assertNotEqual(upcoming, sorted(upcoming))  # Embaralhou de fato.
        self.assertEqual(q.items, self.ITEMS)  # A lista que o usuário vê não muda.

    def test_every_song_plays_once_before_the_queue_ends(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                played = play_until_the_end(queue(self.ITEMS, start=3, seed=seed, shuffle=True))
                self.assertEqual(sorted(played), self.ITEMS)
                self.assertEqual(played[0], 3)

    def test_shuffle_with_repeat_all_reshuffles_each_cycle_without_repeating_at_the_border(self):
        for seed in range(30):
            with self.subTest(seed=seed):
                q = queue(["a", "b", "c"], seed=seed, shuffle=True, repeat=RepeatMode.ALL)
                played = [q.current] + [q.next() for _ in range(8)]  # 3 ciclos completos.
                for cycle in (played[0:3], played[3:6], played[6:9]):
                    self.assertEqual(sorted(cycle), ["a", "b", "c"])
                self.assertTrue(all(x != y for x, y in zip(played, played[1:])))

    def test_cycles_are_not_always_the_same(self):
        q = queue(self.ITEMS, shuffle=True, repeat=RepeatMode.ALL)
        first = [q.current] + [q.next() for _ in range(19)]
        second = [q.next() for _ in range(20)]
        self.assertEqual(sorted(second), self.ITEMS)
        self.assertNotEqual(first, second)

    def test_shuffle_with_repeat_one(self):
        q = queue(self.ITEMS, start=4, shuffle=True, repeat=RepeatMode.ONE)
        self.assertEqual([q.next() for _ in range(3)], [4, 4, 4])
        self.assertNotEqual(q.next(manual=True), 4)

    def test_turning_shuffle_off_continues_in_list_order_from_the_current_song(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        for _ in range(4):
            q.next()
        current = q.current
        q.shuffle = False
        self.assertEqual(q.current, current)
        self.assertEqual(q.upcoming(), self.ITEMS[current + 1:])

    def test_replace_while_shuffled_starts_with_the_chosen_song(self):
        q = queue(self.ITEMS, start=7, shuffle=True)
        self.assertEqual(q.current, 7)
        self.assertEqual(sorted(q.upcoming()), [i for i in self.ITEMS if i != 7])

    def test_appended_songs_play_in_this_cycle_without_replaying_the_others(self):
        q = queue(self.ITEMS[:10], start=0, shuffle=True)
        for _ in range(4):
            q.next()
        already = set(self.ITEMS[:10]) - set(q.upcoming())
        q.append([100, 101, 102])
        rest = q.upcoming()
        self.assertTrue({100, 101, 102} <= set(rest))
        self.assertFalse(already & set(rest))  # O que já tocou não volta.
        self.assertEqual(q.items[-3:], [100, 101, 102])

    def test_play_next_while_shuffled(self):
        q = queue(self.ITEMS, start=3, shuffle=True)
        q.play_next(["x"])
        self.assertEqual(q.next(), "x")

    def test_removing_the_current_song_while_shuffled(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        q.next()
        removed = q.current
        expected_next = q.upcoming()[0]
        self.assertTrue(q.remove(q.current_index))
        self.assertEqual(q.current, expected_next)
        played = play_until_the_end(q)
        self.assertNotIn(removed, played)
        self.assertEqual(len(set(played)), len(played))

    def test_removing_a_song_that_has_not_played_yet_while_shuffled(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        doomed = q.upcoming()[3]
        self.assertFalse(q.remove(q.items.index(doomed)))
        self.assertNotIn(doomed, play_until_the_end(q))

    def test_selecting_a_song_while_shuffled_keeps_the_others_waiting(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        waiting = q.upcoming()
        chosen = waiting[-1]
        self.assertEqual(q.select(chosen), chosen)
        self.assertEqual(sorted(q.upcoming()), sorted(w for w in waiting if w != chosen))

    def test_moving_while_shuffled_does_not_change_the_play_order(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        before = q.upcoming()
        q.move(19, 1)
        self.assertEqual(q.upcoming(), before)
        self.assertEqual(q.items[1], 19)

    def test_previous_while_shuffled_goes_back_to_what_played_before(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        played = [q.current, q.next(), q.next()]
        self.assertEqual([q.previous(0), q.previous(0)], [played[1], played[0]])

    def test_after_the_end_a_shuffled_queue_starts_a_new_cycle(self):
        q = queue(self.ITEMS, start=0, shuffle=True)
        play_until_the_end(q)
        restarted = [q.next()] + [q.next() for _ in range(19)]
        self.assertEqual(sorted(restarted), self.ITEMS)


if __name__ == "__main__":
    unittest.main()
