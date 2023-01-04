import time, glob
import numpy as np
import cv2


def display(label, img, seconds):
    height, width = img.shape[:2]
    img_disp = np.zeros((height, width, 4), dtype=np.uint8)
    img_disp[:,:,:3] = img
    
    with open("/dev/fb0", "wb+") as fp:
        fp.seek(0)
        fp.write(img_disp.tobytes())
    
    time.sleep(seconds)
    return -1


def display_sbs(label, img1, img2, seconds):
    height, width = img1.shape[:2]
    img_disp = np.zeros((height, width, 4), dtype=np.uint8)

    hheight = int(height/2)
    hwidth = int(width/2)
    
    img1 = cv2.resize(img1, (hwidth, hheight), interpolation= cv2.INTER_LINEAR)
    img2 = cv2.resize(img2, (hwidth, hheight), interpolation= cv2.INTER_LINEAR)
    
    img_disp[:hheight, :hwidth, :3] = img1
    img_disp[:hheight, hwidth:, :3] = img2

    with open("/dev/fb0", "wb+") as fp:
        fp.seek(0)
        fp.write(img_disp.tobytes())
    
    time.sleep(seconds)
    return -1

