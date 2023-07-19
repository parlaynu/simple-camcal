import glob
import numpy as np
import cv2


def display(label, img, seconds):
    cv2.imshow(label, img)
    return cv2.waitKey(seconds*1000)


def display_sbs(label, img1, img2, seconds):
    height, width = img1.shape[:2]
    disp = np.zeros((height, 2*width, 3), dtype=np.uint8)

    disp[:, :width, :] = img1
    disp[:, width:, :] = img2

    cv2.imshow(label, disp)
    return cv2.waitKey(seconds*1000)

