#!/usr/bin/env python3
import os.path, time
from itertools import islice


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
        _, image = cam.read()
        yield image


# NOTE: the undistort gstreamer plugin not available with the version of gstreamer with
#       jetpack 4.6.2-b5 (on the jetson nano). If it was available , instead of this, would 
#       add the undistortcamera filter to the camera gstreamer filter.
def undistort(input, calfile):
    import cv2
    
    # load the calibration parameters
    fs = cv2.FileStorage(calfile, cv2.FileStorage_READ)
    cam_matrix = fs.getNode("cameraMatrix").mat()
    cam_dist = fs.getNode("distCoeffs").mat()
    
    # calculate the calibration maps
    img = next(input)
    h, w = img.shape[:2]
    optimal_matrix, roi = cv2.getOptimalNewCameraMatrix(cam_matrix, cam_dist, (w,h), 0, (w,h))
    mapx, mapy = cv2.initUndistortRectifyMap(cam_matrix, cam_dist, None, optimal_matrix, (w,h), 5)        
    
    # and run...
    for img in input:
        img = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)
        yield img


def display(input, mirror):
    import numpy as np
    
    fp = open("/dev/fb0", "wb+")
    
    img = next(input)
    h, w = img.shape[:2]
    buf = np.zeros((h, w, 4), dtype=np.uint8)
    
    for img in input:
        if mirror:
            img = np.flip(img, axis=1)
        buf[:,:,0:3] = img

        fp.seek(0)
        fp.write(buf.tobytes())
        
        yield img


def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--calfile', help='calibration file to load', type=str, default=None)
    parser.add_argument('-m', '--mirror', help='make the display be like a mirror', action='store_true')
    
    args = parser.parse_args()
    
    # create the pipeline
    pipe = camera(1920, 1080)

    if args.calfile is not None:
        if not os.path.exists(args.calfile):
            print("Error: calibration file not found")
            sys.exit(1)
        pipe = undistort(pipe, args.calfile)

    pipe = display(pipe, args.mirror)

    # run the pipeline
    start = time.time()
    for idx, img in enumerate(pipe):
        if idx == 0:
            print(type(img), img.shape, img.dtype)
        if idx > 0 and idx % 300 == 0:
            duration = time.time() - start
            fps = 300/duration
            print(f"frames per second: {fps}")
            start = time.time()
        pass


if __name__ == "__main__":
    main()