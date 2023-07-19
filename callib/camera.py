

def size_for_mode(camera_mode):
    cam_mode_sizes = [
        [3264, 2464],
        [3264, 1848],
        [1920, 1080],
        [1640, 1232],
        [1280, 720],
        [1280, 720],
    ]

    # the default camera mode
    if camera_mode is None:
        camera_mode = 2
    
    if not isinstance(camera_mode, int):
        camera_mode = int(camera_mode)

    width, height = cam_mode_sizes[camera_mode]
    
    return camera_mode, width, height


def mode_for_size(width, height):
    # the default
    if width is None:
        width, height = 1920, 1080

    widths = [3264, 3264, 1920, 1640, 1280]
    heights = [2464, 1848, 1080, 1232, 720]
    
    mode_w = mode_h = -1
    for idx, (w, h) in enumerate(zip(widths, heights)):
        if width <= w:
            mode_w = idx
        if height <= h:
            mode_h = idx
    
    mode = min(mode_w, mode_h)

    return mode

