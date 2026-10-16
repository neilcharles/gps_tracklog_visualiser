from datetime import datetime, timedelta, timezone

import pytest

from backend.tracks import samples_to_points

T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_sorted_deduplicated_utc_and_elevations_filled():
    cet = timezone(timedelta(hours=1))
    points = samples_to_points([
        (T0 + timedelta(seconds=20), 3, 0, 30.0),
        (datetime(2025, 1, 1, 1, 0, 0, tzinfo=cet), 1, 0, None),  # = T0, no elevation
        (T0 + timedelta(seconds=10), 2, 0, None),
        (datetime(2025, 1, 1, 0, 0, 10), 9, 9, 99.0),  # no zone: UTC, so a repeat of T0+10 s, dropped
        (T0 + timedelta(seconds=30), 4, 0, 10.0),
    ])
    assert [(p[0] - T0).seconds for p in points] == [0, 10, 20, 30]
    assert all(p[0].tzinfo == timezone.utc for p in points)
    assert [p[1] for p in points] == [1, 2, 3, 4]
    assert [p[3] for p in points] == [30.0, 30.0, 30.0, 10.0]  # copied before the first known value


def test_interpolates_between_known_elevations():
    points = samples_to_points([
        (T0, 0, 0, 100.0), (T0 + timedelta(seconds=1), 0, 0, None), (T0 + timedelta(seconds=4), 0, 0, 200.0),
    ])
    assert points[1][3] == 125.0


@pytest.mark.parametrize("samples, message", [
    ([(T0, 0, 0, 1.0)], "no timestamped"),
    ([(T0, 0, 0, None), (T0 + timedelta(seconds=1), 0, 0, None)], "no elevation"),
])
def test_unreplayable_samples(samples, message):
    with pytest.raises(ValueError, match=message):
        samples_to_points(samples)
