#!/usr/bin/env python3
import argparse
import sys, os, io
import time
from datetime import datetime
from itertools import count, islice

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import GLib, Gst, GstApp

import numpy as np
import cv2

import callib


def build_gst_pipeline(cam_mode, hflip, vflip):
    # initialise the system
    Gst.init(sys.argv)
    
    # hard coded for now
    cam_mode, cam_width, cam_height = callib.size_for_mode(cam_mode)
    
    # build the pipeline
    nodes = []
    
    node = Gst.ElementFactory.make('nvarguscamerasrc')
    nodes.append(node)
    Gst.util_set_object_arg(node, "sensor-id", "0")
    Gst.util_set_object_arg(node, "bufapi-version", "true")
    Gst.util_set_object_arg(node, "sensor-mode", f"{cam_mode}")
    
    node = Gst.ElementFactory.make('capsfilter')
    nodes.append(node)
    Gst.util_set_object_arg(node, "caps", f"video/x-raw(memory:NVMM), framerate=(fraction)30/1")

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


def camera(appsink, cam_mode):
    cam_mode, cam_width, cam_height = callib.size_for_mode(cam_mode)
    
    for idx in count():
        sample = appsink.pull_sample()
        if sample is None:
            raise RuntimeError("pipeline stopped")

        buffer = sample.get_buffer()
        if buffer is None:
            raise RuntimeError("sample has no buffer")

        data = buffer.extract_dup(0, buffer.get_size())
        
        item = {
            'idx': idx,
            'mode': cam_mode,
            'width': cam_width,
            'height': cam_height,
            'data': data,
        }
        yield item
    

def preview(pipe):
    with open("/dev/fb0", "wb") as fb:
        for item in pipe:
            data = item['data']
            fb.seek(0, io.SEEK_SET)
            fb.write(data)
            yield item
        

def warmup(pipe, *, duration):
    # run the warmup loop
    print(f"warming up...", flush=True)
    start = time.time()
    for item in pipe:
        if time.time() - start > duration:
            break
    
    # now just pass the items through
    print(f"running...", flush=True)
    for item in pipe:
        yield item


def capture(pipe, capture_dir, num_images, time_delay):
    
    current_idx = 0
    current_loop = 0
    loop_max = time_delay * 30
    
    for item in pipe:
        # yield first to make logic below cleaner
        yield item
        
        # check the time
        if current_loop < loop_max:
            if current_loop == 0:
                print(f"{current_idx:02d} waiting...", end="")
            if current_loop % 30 == 0:
                print(f"{current_loop:02d}...", end="", flush=True)
            current_loop += 1
            continue
        print("")
    
        # capture an image
        print(f"{current_idx:02d} capturing...", flush=True)
        image_width = item['width']
        image_height = item['height']
        image_data = item['data']
        
        image_array = np.ndarray((image_height, image_width, 4), np.uint8, image_data)
        image_path = os.path.join(capture_dir, f"image_{current_idx:02d}.jpg")
        cv2.imwrite(image_path, image_array)
        
        current_idx += 1
        current_loop = 0
        
        if current_idx >= num_images:
            break


def build_pipeline(appsink, cam_mode, capture_dir, num_images, time_delay):
    pipe = camera(appsink, cam_mode)
    pipe = preview(pipe)
    pipe = warmup(pipe, duration=5)
    pipe = capture(pipe, capture_dir, num_images, time_delay)
    
    return pipe


def save_config(capture_dir, cam_mode):
    cam_mode, cam_width, cam_height = callib.size_for_mode(cam_mode)
    
    config_file = os.path.join(capture_dir, "capture.txt")
    with open(config_file, "w") as f:
        print("[camera]", file=f)
        print(f"camera-mode={cam_mode}", file=f)
        print(f"camera-width={cam_width}", file=f)
        print(f"camera-height={cam_height}", file=f)
        print("", file=f)
        print("[capture]", file=f)
        print(f"capture-width={cam_width}", file=f)
        print(f"capture-height={cam_height}", file=f)


def run(gpipe, pipe):

    try:
        gpipe.set_state(Gst.State.PLAYING)
        for item in pipe:
            pass

    except KeyboardInterrupt:
        pass
    
    finally:
        gpipe.set_state(Gst.State.NULL)
        gpipe.get_state(Gst.CLOCK_TIME_NONE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-images', help='number of calibration of images to capture in timed-capture mode', type=int, default=5)
    parser.add_argument('-t', '--time-delay', help='seconds between images in timed-capture mode', type=int, default=5)
    parser.add_argument('--hflip', help='horizontal flip (display only)', action='store_true')
    parser.add_argument('--vflip', help='vertical flip (display only)', action='store_true')
    parser.add_argument('capture_root', help='root directory to save captured images', type=str)
    args = parser.parse_args()
    
    # the capture dir
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = os.path.join(args.capture_root, run_stamp)
    os.makedirs(capture_dir, exist_ok=True)
        
    # run the capture
    cam_mode = 2
    gpipe, appsink = build_gst_pipeline(cam_mode, args.hflip, args.vflip)
    if not gpipe:
        return
    
    pipe = build_pipeline(appsink, cam_mode, capture_dir, args.num_images, args.time_delay)
    run(gpipe, pipe)
    
    save_config(capture_dir, cam_mode)


if __name__ == "__main__":
    main()
