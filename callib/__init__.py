import platform

if platform.system() == "Darwin":
    import os
    os.environ['OPENCV_OPENCL_DEVICE'] = 'disabled'

if platform.system() == "Linux":
    from .display_fb import display, display_sbs
else:
    from .display import display, display_sbs

from .camera import size_for_mode, mode_for_size

