"""Frame-to-screen coordinate mapping for click/scroll tools."""


def map_coordinates(
    frame_x: int,
    frame_y: int,
    screen_width: int,
    screen_height: int,
    frame_size: int = 768,
) -> tuple[int, int]:
    """Map coordinates from frame space (e.g. 768x768) to actual screen pixels.

    Args:
        frame_x: X position in the captured frame.
        frame_y: Y position in the captured frame.
        screen_width: Actual screen width in pixels.
        screen_height: Actual screen height in pixels.
        frame_size: Frame dimension (default 768).

    Returns:
        (real_x, real_y) in screen coordinates.
    """
    real_x = int(frame_x * screen_width / frame_size)
    real_y = int(frame_y * screen_height / frame_size)
    return (real_x, real_y)
