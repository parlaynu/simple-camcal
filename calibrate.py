#!/usr/bin/env python3
import sys, time
import argparse
import os.path, glob
import pkg_resources
import configparser

import numpy as np
import cv2

from jinja2 import Template

from callib import display, display_sbs


def detect_corners(image_dir, grid_x, grid_y, grid_size, use_sb_alg):
    # array with 3d coordinates of the grid corners in world space
    objp = np.zeros((grid_x * grid_y, 3), np.float32)
    objp[:,:2] = np.mgrid[0:grid_x, 0:grid_y].T.reshape(-1,2) * grid_size

    # arrays to store object and image coordinates of the corners for each image
    objpoints = []
    imgpoints = []

    # process the images
    images = glob.glob(f'{image_dir}/*.jpg')
    images.sort()
    for fname in images:
        print(f"processing {fname}: ", end="")
    
        img = cv2.imread(fname)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        imgsize = gray.shape
        
        if use_sb_alg:
            ret, corners = cv2.findChessboardCornersSB(gray, (grid_x, grid_y))
        else:
            ret, corners = cv2.findChessboardCorners(gray, (grid_x, grid_y))
            if ret:
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 300, 0.000001)
                corners = cv2.cornerSubPix(gray,corners, (11,11), (-1,-1), criteria)

        print("success" if ret else "failed")

        imgpoints.append(corners)
        objpoints.append(objp if ret else None)
        
    return (objpoints, imgpoints, imgsize)


def calibrate(objpoints, imgpoints, imgsize):
    print("calibrating...")
    
    h, w = imgsize
    
    # filter out all the results that failed
    nobjpoints = []
    nimgpoints = []
    for corners, objects in zip(imgpoints, objpoints):
        if objects is None:
            continue
        nobjpoints.append(objects)
        nimgpoints.append(corners)
    
    # run calibration
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(nobjpoints, nimgpoints, (w, h), None, None)
    if ret == False:
        print("calibration failed")
        sys.exit(0)

    # refine camera matrix
    optimal_cameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 0, (w, h))
    
    results = {
        'camera_mtx': mtx,
        'distortion_coeffs': dist,
        'rvecs': rvecs,
        'tvecs': tvecs,
        'optimal_camera_mtx': optimal_cameramtx,
        'roi': roi
    }
    return results


def display_corners(image_dir, grid_x, grid_y, objpoints, imgpoints, imgsize):
    images = glob.glob(f'{image_dir}/*.jpg')
    images.sort()
    for fname, corners, objects in zip(images, imgpoints, objpoints):
        print(f"displaying {fname}")

        img = cv2.imread(fname)

        cv2.drawChessboardCorners(img, (grid_x, grid_y), corners, False if objects is None else True)
        k = display("corners", img, 2)
        if k != -1 and k == ord('q'):
            break
        


def display_undistorted(image_dir, imgsize, calib_results):
    roi = calib_results['roi']
    mtx, optimal_mtx = calib_results['camera_mtx'], calib_results['optimal_camera_mtx']
    dist = calib_results['distortion_coeffs']

    # load, undistort, and display images
    images = glob.glob(f'{image_dir}/*.jpg')
    images.sort()
    for fname in images:
        print(f"displaying {fname}")

        img = cv2.imread(fname)
        dst = cv2.undistort(img, mtx, dist, None, optimal_mtx)
        
        k = display_sbs("comparison", img, dst, 2)
        if k != -1 and k == ord('q'):
            break


def save_results(image_dir, imgsize, calib_results):
    # get the data to save
    camera_mtx = calib_results['camera_mtx']
    distortion_coeffs = calib_results['distortion_coeffs']
    
    # save the raw calibration data
    calfile = os.path.join(image_dir, "cal-raw.xml")
    
    fs = cv2.FileStorage(calfile, cv2.FileStorage_WRITE)
    fs.write(name="cameraMatrix", val=camera_mtx)
    fs.write(name="distCoeffs", val=distortion_coeffs)
    fs.release()

    # get the camera mode used in the capture
    capfile = os.path.join(image_dir, "capture.txt")
    if os.path.exists(capfile):
        config = configparser.ConfigParser()
        config.read(capfile)
        camera_mode = config['camera']['camera-mode']
    else:
        camera_mode = 2
    
        
    # save the calibration config
    template_str = pkg_resources.resource_string('callib', 'config.tpl').decode('utf-8')
    template = Template(template_str)
    
    height, width = imgsize
    fx, fy, cx, cy = camera_mtx[0,0], camera_mtx[1,1], camera_mtx[0,2], camera_mtx[1,2]
    k0, k1, p0, p1, k2 = distortion_coeffs[0]
    
    focal_length = (fx + fy)/2

    variables = {
        'camera_mode': camera_mode,
        'width': width,
        'height': height,
        'focal_length': focal_length,
        'cx': cx,
        'cy': cy,
        'k0': k0,
        'k1': k1,
        'k2': k2,
        'p0': p0,
        'p1': p1,
    }
    
    confile = os.path.join(image_dir, "cal-config.txt")
    with open(confile, "w") as f:
        f.write(template.render(variables))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-x', '--grid-x', help='number of internal grid corners in x dimension', type=int, default=8)
    parser.add_argument('-y', '--grid-y', help='number of internal grid corners in y dimension', type=int, default=6)
    parser.add_argument('-g', '--grid-size', help='size of the grid squares in real-world units', type=int, default=1)
    parser.add_argument('-s', '--use-sb-alg', help='use the sector based algorithm to detect corners', action='store_true')
    parser.add_argument('-d', '--display', help='display results of processing', action='store_true')
    parser.add_argument('image_dir', help='location of images', type=str)

    args = parser.parse_args()

    # detect the corners in the images
    objpoints, imgpoints, imgsize = detect_corners(args.image_dir, args.grid_x, args.grid_y, args.grid_size, args.use_sb_alg)
    if args.display:
        display_corners(args.image_dir, args.grid_x, args.grid_y, objpoints, imgpoints, imgsize)
    
    # run the calibration
    calib_results = calibrate(objpoints, imgpoints, imgsize)
    if args.display:
        display_undistorted(args.image_dir, imgsize, calib_results)
    
    # save the results
    save_results(args.image_dir, imgsize, calib_results)
    
    
if __name__ == "__main__":
    main()

