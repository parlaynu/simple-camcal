#!/usr/bin/env python3
import sys, os
import argparse
import time, re
from datetime import datetime
from curses import wrapper    
from itertools import islice

import cv2
import numpy as np

import callib


def camera(camera_mode, cam_width, cam_height, cap_width, cap_height):

    gst_str = [
        f"nvarguscamerasrc sensor-id=0 sensor-mode={camera_mode}",
        f"video/x-raw(memory:NVMM), width={cam_width}, height={cam_height}, format=(string)NV12, framerate=(fraction)10/1",
        f"nvvidconv",
        f"video/x-raw, width=(int){cap_width}, height=(int){cap_height}, format=(string)BGRx",
        f"videoconvert",
        f"appsink"
    ]
    print(gst_str, flush=True)

    gst_str = " ! ".join(gst_str)
    
    cam = cv2.VideoCapture(gst_str, cv2.CAP_GSTREAMER)
    while True:
        _, img = cam.read()
        yield { 'image': img }


def auto_capture(input, time_delay, num_images):
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


def display(input, hflip):

    fp = open("/dev/fb0", "wb+")
    
    data = next(input)
    img = data['image']
    height, width = img.shape[:2]
    buf = np.zeros((1080, 1920, 4), dtype=np.uint8)
    
    disp_height, disp_width = min(1080, height), min(1920, width)
    
    for data in input:
        img = data['image']
        if hflip:
            img = np.flip(img, axis=1)
        buf[:height,:width,0:3] = img[:disp_height,:disp_width,0:3]

        fp.seek(0)
        fp.write(buf.tobytes())
        
        yield data


def run(stdscr, pipe, capture_dir):
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


def run_test(pipe, capture_dir):
    idx = 0
    for data in islice(pipe, 4):
        imgpath = os.path.join(capture_dir, f"image{idx:04d}.jpg")
        print(f" capturing to {imgpath}")
        cv2.imwrite(imgpath, data['image'])
        idx += 1
    

def main():
    # parse the command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-images', help='number of calibration of images to capture in timed-capture mode', type=int, default=0)
    parser.add_argument('-t', '--time-delay', help='seconds between images in timed-capture mode', type=int, default=5)
    parser.add_argument('--hflip', help='horizontal flip the image (but not the captured data)', action='store_true')

    parser.add_argument('--mode', 
                            choices=['2', '3', '4', '5'],
                            default=None, const='2',
                            nargs='?',
                            help='the camera mode (default: 2)', 
                        )
    parser.add_argument('-r', '--resolution', help='image capture resolution: widthxheight', type=str, default=None)

    parser.add_argument('capture_root', help='root directory to save captured images', type=str)
    args = parser.parse_args()
    
    # make sure the capture directory exists
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = os.path.join(args.capture_root, run_stamp)
    os.makedirs(capture_dir, exist_ok=True)
    
    # extract the image size to capture
    
    if args.resolution is None:
        cap_width = cap_height = None
    else:
        size_re = re.compile(r"^(\d+)x(\d+)$")
    
        m = size_re.match(args.resolution)
        if m is None:
            print(f"Error: can't process the resolution specification: {args.resolution}")
            sys.exit(1)
    
        cap_width = int(m.group(1))
        cap_height = int(m.group(2))

    # sanitize the arguments
    camera_mode = args.mode
    if camera_mode is None:
        camera_mode = callib.mode_for_size(cap_width, cap_height)
    camera_mode, cam_width, cam_height = callib.size_for_mode(camera_mode)
    if cap_width is None or cap_height is None:
        cap_width, cap_height = cam_width, cam_height
    
    # build the pipeline
    pipe = camera(camera_mode, cam_width, cam_height, cap_width, cap_height)
    if args.num_images > 0:
        pipe = auto_capture(pipe, args.time_delay, args.num_images)
    pipe = display(pipe, args.hflip)
    
    # run the pipeline
    wrapper(run, pipe, capture_dir)
    # run_test(pipe, capture_dir)
    
    # write out the configuration
    config_file = os.path.join(capture_dir, "capture.txt")
    with open(config_file, "w") as f:
        print("[camera]", file=f)
        print(f"camera-mode={camera_mode}", file=f)
        print(f"camera-width={cam_width}", file=f)
        print(f"camera-height={cam_height}", file=f)
        print("", file=f)
        print("[capture]", file=f)
        print(f"capture-width={cap_width}", file=f)
        print(f"capture-height={cap_height}", file=f)


if __name__ == "__main__":
    main()
