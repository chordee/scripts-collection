import numpy as np
import dlib


def get_front_face_rects(img):
    detector = dlib.get_frontal_face_detector()
    rects = detector(img)
    return rects


def convert_rect_to_xywh(rect):
    x = rect.left()
    y = rect.top()
    w = rect.right() - rect.left()
    h = rect.bottom() - rect.top()
    return (x, y, w, h)


def get_68_face_features(img, rect, model):
    features = np.zeros((68, 2))
    predictor = dlib.shape_predictor(model)
    shape = predictor(img, rect)
    for i in range(68):
        features[i] = (shape.part(i).x, shape.part(i).y)
    return features


def get_eye_centers(features):
    lefteye_center = np.mean(features[37:42], axis=0)
    righteye_center = np.mean(features[43:48], axis=0)
    return np.vstack((lefteye_center, righteye_center))


def get_rotate_angle(eye_centers):
    delta = eye_centers[1] - eye_centers[0]
    angle = np.degrees(np.arctan2(delta[1], delta[0]))
    return angle


def get_eyes_center(eye_centers):
    return np.mean(eye_centers, axis=0)


def get_eyes_distance(eye_centers):
    return np.sqrt(np.sum((eye_centers[0] - eye_centers[1])**2))
