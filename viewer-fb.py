#!/usr/bin/env python3
import argparse
import functools, itertools
import sys, io
import time

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import GLib, Gst, GstApp

import cv2
from PIL import Image


def build_pipeline(fps, hflip, vflip):
    # initialise the system
    Gst.init(sys.argv)
    
    # hard coded for now
    camera_mode, cam_width, cam_height = 2, 1920, 1080
    
    # build the pipeline
    nodes = []
    
    node = Gst.ElementFactory.make('nvarguscamerasrc')
    nodes.append(node)
    Gst.util_set_object_arg(node, "sensor-id", "0")
    Gst.util_set_object_arg(node, "bufapi-version", "true")
    Gst.util_set_object_arg(node, "sensor-mode", f"{camera_mode}")
    
    node = Gst.ElementFactory.make('capsfilter')
    nodes.append(node)
    Gst.util_set_object_arg(node, "caps", f"video/x-raw(memory:NVMM), framerate=(fraction){fps}/1")

    node = Gst.ElementFactory.make('nvvideoconvert')
    nodes.append(node)
    
    if hflip and vflip:
        Gst.util_set_object_arg(node, "flip-method", "2")
    elif hflip:
        Gst.util_set_object_arg(node, "flip-method", "4")
    elif vflip:
        Gst.util_set_object_arg(node, "flip-method", "6")
        
    node = Gst.ElementFactory.make('capsfilter')
    nodes.append(node)
    Gst.util_set_object_arg(node, "caps", f"video/x-raw, width=(int){cam_width}, height=(int){cam_height}, format=(string)BGRx")
    
    appsink = node = Gst.ElementFactory.make('appsink')
    nodes.append(node)

    pipe = Gst.Pipeline.new('pipe')
    for node in nodes:
        pipe.add(node)
    
    print("Linking nodes:")
    for n0, n1 in zip(nodes, nodes[1:]):
        print(f"  -> {n0.name}: {len(n0.sinkpads)} {len(n0.srcpads)}")
        r = n0.link(n1)
        if r == False:
            print(f"failed to link nodes {n0.name} and {n1.name}")
            return None, None

    print(f"  -> {n1.name}: {len(n1.sinkpads)} {len(n1.srcpads)}")
    
    return pipe, appsink


def loop(appsink, limit):
    
    start = None
    
    looper = itertools.count
    if limit > 0:
        looper = functools.partial(range, limit)

    with open("/dev/fb0", "wb") as fb:
        for idx in looper():
            # read an image sample
            sample = appsink.pull_sample()
            if sample is None:
                raise RuntimeError("pipeline stopped")
        
            if start is None:
                start = time.time()

            buffer = sample.get_buffer()
            if buffer is None:
                raise RuntimeError("sample has no buffer")
        
            data = buffer.extract_dup(0, buffer.get_size())
        
            fb.seek(0, io.SEEK_SET)
            fb.write(data)
    
    duration = time.time() - start
    print(f"run time: {duration:0.2f}")


def run(pipe, appsink, limit):

    try:
        pipe.set_state(Gst.State.PLAYING)
        loop(appsink, limit)

    except KeyboardInterrupt:
        pass
    
    finally:
        pipe.set_state(Gst.State.NULL)
        pipe.get_state(Gst.CLOCK_TIME_NONE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--limit', help='limit the number of frames to send', type=int, default=0)
    parser.add_argument('-r', '--fps', help='camera frame rate', type=int, default=30)
    parser.add_argument('--hflip', help='flip the image horizontally', action='store_true')
    parser.add_argument('--vflip', help='flip the image vertically', action='store_true')
    args = parser.parse_args()
    
        
    pipe, appsink = build_pipeline(args.fps, args.hflip, args.vflip)
    if pipe:
        run(pipe, appsink, args.limit)


if __name__ == "__main__":
    main()
