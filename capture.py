#!/usr/bin/env python3

def camera(xsize, ysize):
    import cv2
    
    gst_str = [
        f"nvarguscamerasrc sensor-id=0",
        f"video/x-raw(memory:NVMM), width=1920, height=1080, format=(string)NV12, framerate=(fraction)10/1",
        f"nvvidconv",
        f"video/x-raw, width=(int){xsize}, height=(int){ysize}, format=(string)BGRx",
        f"videoconvert",
        f"appsink"
    ]
    gst_str = " ! ".join(gst_str)
    
    cam = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)
    while True:
        _, img = cam.read()
        yield { 'image': img }


def auto_capture(input, time_delay, num_images):
    import time
    
    count = 0
    start_time = None
    
    for data in input:
        if start_time is None:
            start_time = time.time()
        
        duration = time.time() - start_time
        
        # implement the traffic lights...
        img = data['image']
        h, w, _ = img.shape
        
        x0, x1 = int(w/2-h/6), int(w/2+h/6)
        y0, y1 = int(h/2-h/6), int(h/2+h/6)
        
        if time_delay - duration > 3:
            img[y0:y1, x0:x1, :] = (0, 0, 255)
        elif time_delay - duration > 2:
            img[y0:y1, x0:x1, :] = (0, 255, 255)
        elif time_delay - duration > 1:
            img[y0:y1, x0:x1, :] = (0, 255, 0)
        
        # if we're exceeded the time delay, set the save flag
        if duration > time_delay:
            data['save'] = True
            start_time = None
            count += 1

        # if we've capture enough images, signal to finish
        if count >= num_images:
            data['over'] = True

        yield data


def display(input, mirror):
    import numpy as np

    fp = open("/dev/fb0", "wb+")
    
    data = next(input)
    img = data['image']
    height, width = img.shape[:2]
    buf = np.zeros((height, width, 4), dtype=np.uint8)
    
    for data in input:
        img = data['image']
        if mirror:
            img = np.flip(img, axis=1)
        buf[:,:,0:3] = img

        fp.seek(0)
        fp.write(buf.tobytes())
        
        yield data


def run(stdscr, pipe, capture_dir):
    import os
    import cv2

    stdscr.clear()
    stdscr.nodelay(True)
    
    idx = 0
    stdscr.addstr(idx, 0, "press 'c' to capture, 'q' to quit: ")
    for data in pipe:
        
        try:
            key = stdscr.getkey()
        except:
            key = ""

        # accept space bar to capture as well as 'c'
        if key == " ":
            key = "c"
        
        stdscr.addstr(key)
        if key == "q":
            break
        
        if data.get("save", False) or key == "c":
            imgpath = os.path.join(capture_dir, f"image{idx:04d}.jpg")
            stdscr.addstr(f" capturing to {imgpath}")
            cv2.imwrite(imgpath, data['image'])
            idx += 1
        
        if data.get("over", False):
            break

        stdscr.addstr(idx, 0, "press 'c' or 'space' to capture, 'q' to quit: ")
    
    pass


def main():
    import sys, os
    import argparse, re
    from datetime import datetime
    from curses import wrapper
    
    # parse the command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--resolution', help='image capture resolution: widthxheight', type=str, default='1920x1080')
    parser.add_argument('-n', '--num-images', help='number of calibration of images to capture in timed-capture mode', type=int, default=0)
    parser.add_argument('-t', '--time-delay', help='seconds between images in timed-capture mode', type=int, default=5)
    parser.add_argument('-m', '--mirror', help='mirror the display (but not the captured data)', action='store_true')
    parser.add_argument('capture_root', help='root directory to save captured images', type=str)
    args = parser.parse_args()
    
    # make sure the capture directory exists
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = os.path.join(args.capture_root, run_stamp)
    os.makedirs(capture_dir, exist_ok=True)
    
    # extract the image size to capture
    size_re = re.compile(r"^(\d+)x(\d+)$")
    
    m = size_re.match(args.resolution)
    if m is None:
        print(f"Error: can't process the resolution specification: {args.resolution}")
        sys.exit(1)
    
    width = int(m.group(1))
    height = int(m.group(2))

    # build the pipeline
    pipe = camera(width, height)
    if args.num_images > 0:
        pipe = auto_capture(pipe, args.time_delay, args.num_images)
    pipe = display(pipe, args.mirror)
    
    # run the pipeline
    wrapper(run, pipe, capture_dir)


if __name__ == "__main__":
    main()
