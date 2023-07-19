# Simple Camera Calibration

This is a set of tools to calibrate a camera to correct for lens and camera geometric distortions. 
An example of images captured without and with the calibration applied is below:

<table>
    <tr>
        <td><img src="docs/img-nocal.png"></td>
        <td><img src="docs/img-cal.png"></td>
    </tr>
</table>

It has been built to run on a Jetson Nano using the CSI camera interface.

There are four tools in the toolkit:

* viewer.py - simple viewer that can optionally load a calibration matrix
* capture.py - tool to capture a sequence of calibration images
* calibrate.py - process the captured images 
* recorder.py - records images to disk, optionally using a calibration matrix

The viewer and capture applications are built using 
[Gstreamer](https://gstreamer.freedesktop.org/documentation/tutorials/index.html?gi-language=python) 
with Nvidia's [deepstream](https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Overview.html) 
extensions. The calibration tool is built using [OpenCV](https://opencv.org/) and based on this 
[tutorial](https://docs.opencv.org/4.6.0/dc/dbb/tutorial_py_calibration.html).

The basic set of steps involve in the calibration are:

* create a checkerboard calibration image
* capture a range of images of the checkerboard
* create calibration matrix from the images
* run the viewer with the generated calibration configuration

Full documentation for the tools can be found by running them with the `--help` flag, or in this
[document](docs/tools.md)

## Example

This section provides an example of walking through the process and using the generated calibration
files. 

### Setup

The examples here are for a system without a GUI running, so the first step is to turn it off:

    sudo systemctl isolate multi-user.target
    sudo systemctl set-default multi-user.target

The rest of the examples assume that you are accessing the jetson nano using ssh, and the HDMI
output is connected to a display.

Install the extra packages needed on the jetson to run the applications. This needs to be installed
in the user's path or the system - it can't be in a virtualenv as need to use the libraries that
are part of the jetpack, not what's available through pip.

    pip3 install -r requirements.txt

Make sure the gstreamer packages are installed on your system. This is what I have installed:

    sudo apt install gstreamer1.0-tools nvidia-l4t-gstreamer gstreamer1.0-libav gstreamer1.0-alsa
    sudo apt install gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly

There are possibly other things that need to be installed. If I ever start from scratch again, I'll take
better notes and update here.

### Viewing

To view the images and get a feeling for the distortion, run the `viewer.py` app:

    $ ./viewer.py

Line up some straight edges next to the edge of the image to get a good feeling for the amount
of distortion.

Stop the viewer with `ctrl-c`.

### Capturing Images

You'll need a checkerboard ready before running this - see the reference section.

Run the capture application:

    $ ./capture.py -n 20 -t 5 --hflip local

This will capture 20 images, with a delay of 5 seconds between image (so you have time to get your 
checkboard into the next position). It also flips the image for display so it looks like you're in
front of a mirror - I find this easier to position the checkerboard while watching the display.

The captured images along with the capture config are saved to a timestamp directory under `local`
like this:

    $ ls -l local/
    total 8
    drwxrwxr-x 2 paul paul 4096 May 18 01:19 20230518-011818

    $ ls -l local/20230518-011818
    total 45308
    -rw-rw-r-- 1 paul paul     110 May 18 01:18 capture.txt
    -rw-rw-r-- 1 paul paul 5122545 May 18 01:18 image0000.png
    -rw-rw-r-- 1 paul paul 5120516 May 18 01:18 image0001.png
    ....
    -rw-rw-r-- 1 paul paul 5118010 May 18 01:20 image0018.png
    -rw-rw-r-- 1 paul paul 5303458 May 18 01:20 image0019.png

The contents of the capture config file are like this:

    [camera]
    camera-mode=2
    camera-width=1920
    camera-height=1080
    [capture]
    capture-width=1920
    capture-height=1080


### Calibrating

Before calibrating, it's worth reviewing the images that you've captured and removing any bad captures.
A bad image could be blurred from motion, or in the checkerboard partially off screen. You'll get better 
results if you remove any bad images.

Once you have the images, you can run the calibration.

    $ ./calibrate.py -x 8 -y 6 -g 2 local/20230518-011818/
    processing local/20230518-011818/image0000.jpg: success
    processing local/20230518-011818/image0001.jpg: success
    ...
    processing local/20230518-011818/image0018.jpg: success
    processing local/20230518-011818/image0019.jpg: success
    calibrating...

This creates two files in the image directory with the calibration information:

    -rw-rw-r-- 1 paul paul    478 May 18 01:22 cal-config.txt
    -rw-rw-r-- 1 paul paul    533 May 18 01:22 cal-raw.xml

The file `cal-config.txt` is in the format needed for the viewer and looks like this:

    [property]
    camera-mode=2
    output-width=1920
    output-height=1080
    num-batch-buffers=1
    [surface0]
    # 3=PerspectivePerspective
    projection-type=3
    width=1920
    height=1080
    focal-length=1588.8534809922935
    src-x0=1048.3737261822962
    src-y0=506.03150358949677
    distortion=-0.3561592743907544;0.19877723536005001;-0.07516529290785304;-0.002437501887250334;-0.002127113862300699

This is fed to the nvidia deepstream nvdewarper node. The documentation for that node is 
[here](https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_plugin_gst-nvdewarper.html)
with an explanation of what all the parameters mean.

### Viewing With Correction

Now that you've got the calibration file, you can run the viewer with the correction:

    $ ./viewer.py local/20230518-011818/cal-config.txt

You should be seeing straight edges in the image.

## Reference

There are a range of calibration checkerboard images available on the internet - here are a couple
of sources:

* https://github.com/opencv/opencv/blob/master/doc/pattern.png
* https://markhedleyjones.com/projects/calibration-checkerboard-collection

You can also use an OpenCV tool to generate calibration patterns as described in this tutorial:

* https://docs.opencv.org/4.x/da/d0d/tutorial_camera_calibration_pattern.html

Here are some videos on what it's all about and how to perform a calibration:

* https://www.youtube.com/watch?v=26nV4oDLiqc
* https://www.youtube.com/watch?v=-9He7Nu3u8s


