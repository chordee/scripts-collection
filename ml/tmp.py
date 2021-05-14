import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import EXR_utils
import cv2
import numpy as np
import face_detect_utils

if __name__ == "__main__":

    model = "D:/tmp/shape_predictor.dat"
    img = cv2.imread("D:/tmp/higher.png")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    rects = face_detect_utils.get_front_face_rects(img)
    rect = rects[0]
    features = face_detect_utils.get_68_face_features(img, rect, model)
    eye_centers = face_detect_utils.get_eye_centers(features)
    print(eye_centers)
    print(face_detect_utils.get_eyes_distance(eye_centers))
    print(face_detect_utils.get_eyes_center(eye_centers))
    print(face_detect_utils.get_rotate_angle(eye_centers))
