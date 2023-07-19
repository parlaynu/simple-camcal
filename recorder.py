#!/usr/bin/env python3
import sys, re
import argparse
import os
import time
from datetime import datetime
import configparser

import gi
gi.require_version('Gst', '1.0')
gi.require_version("GstApp", "1.0")

from gi.repository import GLib, Gst, GstApp

import callib


## functions to build pipeline

def link_nodes(name, pipe, nodes):
    
    print(f"{name}:")
    
    # add the nodes to the pipeline
    for node in nodes:
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
            raise ValueError(f"-> failed to link nodes {n0.name} and {n1.name}")
            return False

        print(f"-> linking {n0.name}: {len(n0.sinkpads)} {len(n0.srcpads)}")

    print(f"-> linking {n1.name}: {len(n1.sinkpads)} {len(n1.srcpads)}")

    return True


def build_pipeline(camera_mode, cam_width, cam_height, cam_calfile):
    
    # create the pipeline
    pipe = Gst.Pipeline.new('recorder')
    
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
        
    node = Gst.ElementFactory.make('nvvideoconvert')
    nodes.append(node)

    if cam_calfile is not None:
        node = Gst.ElementFactory.make('capsfilter')
        nodes.append(node)
        Gst.util_set_object_arg(node, "caps", f"video/x-raw(memory:NVMM), width=(int){cam_width}, height=(int){cam_height}, format=(string)RGBA")

        node = Gst.ElementFactory.make('nvdewarper')
        nodes.append(node)
        Gst.util_set_object_arg(node, "config-file", cam_calfile)
        Gst.util_set_object_arg(node, "source-id", "6")
        Gst.util_set_object_arg(node, "num-batch-buffers", "1")

        node = Gst.ElementFactory.make('nvvideoconvert')
        nodes.append(node)

    node = Gst.ElementFactory.make('pngenc')
    nodes.append(node)

    sink = node = Gst.ElementFactory.make('appsink')
    nodes.append(node)
    Gst.util_set_object_arg(node, "emit-signals", "true")
    
    if link_nodes("Recorder Pipeine", pipe, nodes) == False:
        return None, None
    
    return pipe, sink


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

def newsample_cb(appsink, tracker):

    # pull the sample
    sample = appsink.pull_sample()
    if sample is None:
        return Gst.FlowReturn.OK
    
    # check the timeout
    if time.time() < tracker['next']:
        print(".", end="", flush=True)
        return Gst.FlowReturn.OK
    print("")
    
    # save the image
    name = os.path.join(tracker['capture_dir'], f"image{tracker['count']:04d}.png")
    print(f"saving image to {name}", flush=True)

    buffer = sample.get_buffer()
    data = buffer.extract_dup(0, buffer.get_size())
    with open(name, "wb") as f:
        f.write(data)
        
    tracker['count'] = tracker['count'] + 1
    tracker['next'] = time.time() + tracker['delay']

    if tracker['count'] >= tracker['total']:
        tracker['loop'].quit()
    
    return Gst.FlowReturn.OK


## run the application

def run(pipe, sink, capture_dir, num_images, delay):
    
    bus = pipe.get_bus()
    bus.add_signal_watch()
    
    # create the main loop and connect the message callback
    loop = GLib.MainLoop()
    bus.connect("message", bus_cb, loop)
    
    tracker = {
        'count': 0,
        'total': num_images,
        'delay': delay,
        'next': time.time() + 5,
        'capture_dir': capture_dir,
        'loop': loop
    }
    sink.connect("new-sample", newsample_cb, tracker)
    
    try:
        pipe.set_state(Gst.State.PLAYING)
        loop.run()
        
    except KeyboardInterrupt:
        pass
    
    pipe.set_state(Gst.State.NULL)
    pipe.get_state(Gst.CLOCK_TIME_NONE)
    
    return 0


def main():
    # initialise the gst library
    Gst.init(sys.argv)

    # parse application arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-images', help='number of calibration of images to capture in timed-capture mode', type=int, default=2)
    parser.add_argument('-t', '--time-delay', help='seconds between images in timed-capture mode', type=int, default=5)
    parser.add_argument('--mode',
                            choices=['2', '3', '4', '5'],
                            default=None, const='2',
                            nargs='?',
                            help='the camera mode (default: 2)', 
                        )
    parser.add_argument('capture_root', help='root directory to save captured images', type=str)
    parser.add_argument('calconfig', help='calibration config file', type=str, nargs='?', default=None)
    args = parser.parse_args()
    
    # get the camera mode
    #  order: command line, calibration file, default
    camera_mode = args.mode
    if camera_mode is None and args.calconfig is not None:
        config = configparser.ConfigParser()
        config.read(args.calconfig)
        camera_mode = config['property'].get('camera-mode', None)

    camera_mode, cam_width, cam_height = callib.size_for_mode(camera_mode)
    
    # make sure the capture directory exists
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    capture_dir = os.path.join(args.capture_root, run_stamp)
    os.makedirs(capture_dir, exist_ok=True)
    
    pipe, sink = build_pipeline(camera_mode, cam_width, cam_height, args.calconfig)

    if pipe is None:
        return 1
    
    run(pipe, sink, capture_dir, args.num_images, args.time_delay)


if __name__ == "__main__":
    sys.exit(main())

