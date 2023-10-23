#!/usr/bin/env python3
import sys
import argparse
import configparser

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

import callib


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


def build_pipeline(camera_mode, hflip, vflip, calfile):
    
    # extract the camera mode, width, and height from the calfile
    cal_width = cal_height = None
    if calfile is not None:
        config = configparser.ConfigParser()
        config.read(calfile)
        cal_width = config['property']['output-width']
        cal_height = config['property']['output-height']
        if camera_mode is None:
            camera_mode = config['property'].get('camera-mode', None)

    camera_mode, cam_width, cam_height = callib.size_for_mode(camera_mode)
    if cal_width is None or cal_height is None:
        cal_width, cal_height = cam_width, cam_height
    
    print("Display Settings")
    print(f"  -> cam mode: {camera_mode}")
    print(f"  -> cam res: {cam_width} {cam_height}")
    print(f"  -> cal res: {cal_width} {cal_height}")

    # build the pipeline
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
    if hflip and vflip:
        Gst.util_set_object_arg(node, "flip-method", "rotate-180")
    elif hflip:
        Gst.util_set_object_arg(node, "flip-method", "horizontal-flip")
    elif vflip:
        Gst.util_set_object_arg(node, "flip-method", "vertical-flip")

    if calfile is not None:
        node = Gst.ElementFactory.make('capsfilter')
        nodes.append(node)
        Gst.util_set_object_arg(node, "caps", f"video/x-raw(memory:NVMM), width=(int){cal_width}, height=(int){cal_height}, format=(string)RGBA")

        node = Gst.ElementFactory.make('nvdewarper')
        nodes.append(node)
        Gst.util_set_object_arg(node, "config-file", calfile)
        Gst.util_set_object_arg(node, "source-id", "6")
        Gst.util_set_object_arg(node, "num-batch-buffers", "1")

    node = Gst.ElementFactory.make('autovideosink')
    nodes.append(node)

    pipe = Gst.Pipeline.new('viewer')
    for node in nodes:
        pipe.add(node)
    
    print("Display Pipeline")
    for n0, n1 in zip(nodes, nodes[1:]):
        print(f"  -> {n0.name}: {len(n0.sinkpads)} {len(n0.srcpads)}")
        r = n0.link(n1)
        if r == False:
            print(f"failed to link nodes {n0.name} and {n1.name}")
            return None

    print(f"  -> {n1.name}: {len(n1.sinkpads)} {len(n1.srcpads)}")
    
    return pipe


def run_pipeline(pipe):
    
    bus = pipe.get_bus()
    bus.add_signal_watch()
    
    try:
        loop = GLib.MainLoop()
        bus.connect("message", bus_cb, loop)
        
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
    parser.add_argument('--hflip', help='horizontal flip', action='store_true')
    parser.add_argument('--vflip', help='vertical flip', action='store_true')
    parser.add_argument('--mode', 
                            choices=['2', '3', '4', '5'],
                            default=2,
                            help='the camera mode (default: 2)', 
                        )
    parser.add_argument('calconfig', help='calibration config file', type=str, nargs='?', default=None)
    args = parser.parse_args()
        
    # build and run the pipeline
    pipe = build_pipeline(args.mode, args.hflip, args.vflip, args.calconfig)
    if pipe is None:
        return 1
    
    return run_pipeline(pipe)
    

if __name__ == "__main__":
    sys.exit(main())


