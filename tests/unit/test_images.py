import numpy as np

from spritemotion.sprites.images import blank_canvas, fingerprint, mirror_canvas, mirror_x, opaque_bounds, place


def dot(width=8, height=6, x=1, y=2, rgb=(10, 20, 30)):
    canvas = blank_canvas(width, height)
    canvas[y, x] = (*rgb, 255)
    return canvas


def test_mirror_canvas_about_centre_matches_mirror_x():
    canvas = dot(x=1)
    mirrored = mirror_canvas(canvas, (8 - 1) / 2)
    assert mirrored[2, int(mirror_x(1, 3.5))][3] == 255
    assert np.array_equal(mirror_canvas(mirrored, 3.5), canvas)


def test_mirror_canvas_about_offset_axis_shifts_columns():
    canvas = dot(x=1)
    mirrored = mirror_canvas(canvas, 4.0)  # column 1 -> 7
    assert mirrored[2, 7][3] == 255 and mirrored[:, :7, 3].sum() == 0


def test_fingerprint_ignores_colour_under_transparent_pixels():
    a, b = dot(), dot()
    b[0, 0] = (99, 99, 99, 0)
    assert fingerprint(a) == fingerprint(b)
    b[2, 1, 0] = 11
    assert fingerprint(a) != fingerprint(b)


def test_opaque_bounds_is_half_open():
    assert opaque_bounds(dot(x=3, y=4)) == [3, 4, 4, 5]
    assert opaque_bounds(blank_canvas(4, 4)) is None


def test_place_rejects_images_that_do_not_fit():
    canvas = blank_canvas(4, 4)
    place(canvas, dot(2, 2, 0, 0), (2, 2))
    try:
        place(canvas, dot(2, 2, 0, 0), (3, 3))
    except ValueError:
        return
    raise AssertionError("expected ValueError")
