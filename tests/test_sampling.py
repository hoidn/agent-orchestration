from tests.sampling import keep

IDS = [f"tests/test_m{i % 40}.py::test_case[{i}]" for i in range(5000)]


def test_sample_is_about_the_requested_share_and_repeatable():
    chosen = [n for n in IDS if keep(n, 10, seed=7)]
    assert 400 < len(chosen) < 600
    assert chosen == [n for n in IDS if keep(n, 10, seed=7)]


def test_a_different_seed_picks_different_tests():
    assert {n for n in IDS if keep(n, 10, seed=7)} != {n for n in IDS if keep(n, 10, seed=8)}


def test_bounds_keep_everything_or_nothing():
    assert all(keep(n, 100, seed=1) for n in IDS)
    assert not any(keep(n, 0, seed=1) for n in IDS)


def test_the_seed_is_kept_after_a_failure_and_redrawn_after_a_pass(tmp_path):
    from tests.sampling import choose_seed, record_outcome

    first, reused = choose_seed(tmp_path, 10)
    assert not reused
    record_outcome(tmp_path, 10, first, passed=False)
    assert choose_seed(tmp_path, 10) == (first, True)
    assert choose_seed(tmp_path, 25)[1] is False  # another share is another sample
    record_outcome(tmp_path, 10, first, passed=True)
    assert choose_seed(tmp_path, 10)[1] is False
