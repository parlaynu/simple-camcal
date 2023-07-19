#!/usr/bin/env python3
import sys, re
import argparse
import os
from datetime import datetime
import threading, time
import queue

import gi
gi.require_version('Gst', '1.0')
gi.require_version("GstApp", "1.0")

from gi.repository import GLib, Gst, GstApp

import callib


## functions to build pipeline

def link_nodes(name, pipe, nodes, add0):
    
    print(f"{name}:")
    
    # add the nodes to the pipeline
    ns = nodes if add0 == True else nodes[1:]
    for node in ns:
        print(f"-> adding {node.name}", flush=True)
        pipe.add(node)
    
    # create the links
    for n0, n1 in zip(nodes, nodes[1:]):
        if n0.name == "tee":
            srcpad = n0.get_request_pad("src_%u")
            snkpad = n1.get_static_pad("sink")
            r = srcpad.link(snkpad)
        else:
            r = n0.link(n1)

        if r == False:
            raise ValueError(f"- failed to link nodes {n0.name} and {n1.name}")

        print(f"-> linking {n0.name}: {len(n0.sinkpads)} {len(n0.srcpads)}")

    print(f"-> linking {n1.name}: {len(n1.sinkpads)} {len(n1.srcpads)}")


def build_pipeline(que, camera_mode, cam_width, cam_height, hflip, vflip):
    
    # create the pipeline
    pipe = Gst.Pipeline.new('viewer')
    
    # the viewer path
    nodes = []    
    
    node = Gst.ElementFactory.make('nvarguscamerasrc')
    nodes.append(node)
    Gst.util_set_object_arg(node, "sensor-id", "0")
    Gst.util_set_object_arg(node, "bufapi-version", "true")
    Gst.util_set_object_arg(node, "sensor-mode", f"{camera_mode}")
    
    node = Gst.ElementFactory.make('capsfilter')
    nodes.append(node)
    Gst.util_set_object_arg(node, "caps", f"video/x-raw(memory:NVMM), width=(int){cam_width}, height=(int){cam_height}, format=(string)NV12")
    
    tee = node = Gst.ElementFactory.make('tee')
    nodes.append(node)

    node = Gst.ElementFactory.make('queue')
    nodes.append(node)
    
    node = Gst.ElementFactory.make('nvvideoconvert')
    nodes.append(node)
    if hflip and vflip:
        Gst.util_set_object_arg(node, "flip-method", "rotate-180")
    elif hflip:
        Gst.util_set_object_arg(node, "flip-method", "horizontal-flip")
    elif vflip:
        Gst.util_set_object_arg(node, "flip-method", "vertical-flip")

    node = Gst.ElementFactory.make('autovideosink')
    nodes.append(node)

    link_nodes("Display Pipeline", pipe, nodes, True)

    # the file save path
    nodes = []
    nodes.append(tee)
    
    node = Gst.ElementFactory.make('queue')
    nodes.append(node)
    Gst.util_set_object_arg(node, "leaky", "2")
    Gst.util_set_object_arg(node, "max-size-buffers", "15")
    
    node = Gst.ElementFactory.make('nvvideoconvert')
    nodes.append(node)

    node = Gst.ElementFactory.make('pngenc')
    nodes.append(node)

    node = Gst.ElementFactory.make('appsink')
    nodes.append(node)
    Gst.util_set_object_arg(node, "emit-signals", "true")
    
    node.connect("new-sample", newsample_cb, que)

    link_nodes("Filesave Pipeine", pipe, nodes, False)
    
    return pipe


## callback function for the bus

def bus_cb(bus, message, loop):
    t = message.type
    if t == Gst.MessageType.EOS:
        sys.stdout.write("End-of-stream\n")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        sys.stderr.write("Error: %s: %s\n" % (err, debug))
        loop.quit()

    return True


## callback function for the appsink

def newsample_cb(appsink, que):

    # pull the sample
    sample = appsink.pull_sample()
    if sample is None:
        return Gst.FlowReturn.OK
    
    # if we have a message on the queue, it's time to save an image
    # if there's no message, just return
    try:
        name = que.get(False)
    except queue.Empty:
        return Gst.FlowReturn.OK
    
    # save the image
    print(f"saving image to {name}", flush=True)

    buffer = sample.get_buffer()
    data = buffer.extract_dup(0, buffer.get_size())
    with open(name, "wb") as f:
        f.write(data)
    
    return Gst.FlowReturn.OK


## the worker - manages the timeouts and initiates the
##   capture of an image

def run_worker(event, loop, que, capture_dir, num_images, delay):

    time.sleep(2)
    print("warming up...", flush=True, end="")
    
    for d in range(delay):
        if event.is_set():
            return
        time.sleep(1)
        print(f"{d:02d}...", flush=True, end="")
    print()

    for idx in range(num_images):
        print("countdown...", flush=True, end="")
        for d in range(delay):
            if event.is_set():
                return
            time.sleep(1)
            print(f"{d:02d}...", flush=True, end="")
        print()

        imgpath = os.path.join(capture_dir, f"image{idx:04d}.png")
        que.put(imgpath)
        
        time.sleep(2)
    
    # shut everything down
    loop.quit()


## run the application

def run(pipe, que, capture_dir, num_images, delay):
    
    bus = pipe.get_bus()
    bus.add_signal_watch()
    
    # create the main loop and connect the message callback
    loop = GLib.MainLoop()
    bus.connect("message", bus_cb, loop)
    
    # start the worker thread
    event = threading.Event()
    t = threading.Thread(target=run_worker, args=(event, loop, que, capture_dir, num_images, delay))
    t.start()
    
    try:
        pipe.set_state(Gst.State.PLAYING)
        loop.run()
        
    except KeyboardInterrupt:
        event.set()
    
    t.join()
    pipe.set_state(Gst.State.NULL)
    pipe.get_state(Gst.CLOCK_TIME_NONE)
    
    return 0


def main():
    # initialise the gst library
    Gst.init(sys.argv)

    # parse application arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-images', help='number of calibration of images to capture in timed-capture mode', type=int, default=5)
    parser.add_argument('-t', '--time-delay', help='seconds between images in timed-capture mode', type=int, default=5)
    parser.add_argument('--hflip', help='horizontal flip (display only)', action='store_true')
    parser.add_argument('--vflip', help='vertical flip (display only)', action='store_true')
    parser.add_argument('--mode', 
                            choices=['2', '3', '4', '5'],
                            default=None, const='2',
                            nargs='?',
                            help='the camera mode (default: 2)', 
                        )
    parser.add_argument('capture_root', help='root directory to save captured images', type=str)
    args = parser.parse_args()
    
    # get camera width/height
    camera_mode, cam_width, cam_height = callib.size_for_mode(args.mode)
    
    # make sure the capture directory exists
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = os.path.join(args.capture_root, run_stamp)
    os.makedirs(capture_dir, exist_ok=True)
    
    # save the capture config
    save_config(capture_dir, camera_mode, cam_width, cam_height)
    
    # build and run the pipeline
    que = queue.Queue()
    
    pipe = build_pipeline(que, camera_mode, cam_width, cam_height, args.hflip, args.vflip)
    if pipe is None:
        return 1
    
    run(pipe, que, capture_dir, args.num_images, args.time_delay)
    

def save_config(capture_dir, camera_mode, cam_width, cam_height):

    config_file = os.path.join(capture_dir, "capture.txt")
    with open(config_file, "w") as f:
        print("[camera]", file=f)
        print(f"camera-mode={camera_mode}", file=f)
        print(f"camera-width={cam_width}", file=f)
        print(f"camera-height={cam_height}", file=f)
        print("", file=f)
        print("[capture]", file=f)
        print(f"capture-width={cam_width}", file=f)
        print(f"capture-height={cam_height}", file=f)


if __name__ == "__main__":
    sys.exit(main())

