# TODO - Implement these methods:
# - ORB feature matching
# - Optical Flow for object tracking (mostly non-character objects, object that stay consistent in shape/form/orientation)
# - Cascade Classifier for character detection
# - Also implement framework for training a cascade classifier
# - Also implement framework for building a dataset for training a cascade classifier
# - Rebuild a new model while training at chronos to test it out


##### ORB FEATURE MATCHING ####
import cv2
import numpy as np
import os
import time

from botting.utilities import client_handler, take_screenshot
from royals import royals_ign_finder
from paths import ROOT

HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)
# Load the template image (object/tile)
templates = [
    cv2.imread(
        os.path.join(ROOT, f'royals/assets/game_files/mobs/images/Slimy/{img}'),
        cv2.IMREAD_GRAYSCALE
    ) for img in os.listdir(
        os.path.join(ROOT, 'royals/assets/game_files/mobs/images/Slimy')
    )
]
templates += [cv2.flip(template, 1) for template in templates]
# template_height, template_width = template.shape[:2]

# Initialize ORB detector
orb = cv2.ORB_create(
    nfeatures=1000,
    scaleFactor=1.2,
    nlevels=8,
    edgeThreshold=31,
    firstLevel=0,
    WTA_K=2,
    scoreType=cv2.ORB_HARRIS_SCORE,
    patchSize=31,
    fastThreshold=20
)

# Compute keypoints and descriptors for the template
# kp_template, des_template = orb.detectAndCompute(template, None)


# Function to detect the template in the game window using ORB
def detect_template_orb(game_window, templates):
    # Convert game window to grayscale
    gray_window = cv2.cvtColor(game_window, cv2.COLOR_BGR2GRAY)

    # Compute keypoints and descriptors for the game window
    kp_window, des_window = orb.detectAndCompute(gray_window, None)
    # Match descriptors using BFMatcher
    # bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)

    for template in templates:
        # Compute keypoints and descriptors for the template
        kp_template, des_template = orb.detectAndCompute(template, None)
        matches = bf.knnMatch(des_template, des_window, k=2)
        # matches = bf.match(des_template, des_window)
        # min_distance = min(m.distance for m in matches)
        # good_matches = [m for m in matches if m.distance < 1.2 * min_distance]
        good_matches = []
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)
        matched_image = cv2.drawMatches(template, kp_template, game_window, kp_window, good_matches, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)

        for m in good_matches:
            x, y = kp_window[m.trainIdx].pt
            w, h = template.shape[::-1]
            cv2.rectangle(game_window, (int(x), int(y)), (int(x + w), int(y + h)), (0, 255, 0), 2)

    cv2.imshow('Matched Image', game_window)
    cv2.waitKey(1)

        # # Sort matches by distance
        # matches = sorted(matches, key=lambda x: x.distance)
        # # Draw matches (for visualization)
        # # result = cv2.drawMatches(template, kp_template, game_window, kp_window,
        # #                          matches[:10], None,
        # #                          flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        # # cv2.imshow('result', result)
        # # cv2.waitKey(1)
        #
        # if len(matches) > 20:
        #     points_template = np.float32(
        #         [kp_template[m.queryIdx].pt for m in matches]
        #     ).reshape(-1, 1, 2)
        #     points_window = np.float32(
        #         [kp_window[m.trainIdx].pt for m in matches]
        #     ).reshape(-1, 1, 2)
        #
        #     # Find homography
        #     M, mask = cv2.findHomography(points_template, points_window, cv2.RANSAC, 5.0)
        #     if M is not None:
        #         # Use homography to find the bounding box of the detected template
        #         h, w = template.shape
        #         pts = np.float32([[0, 0], [0, h], [w, h], [w, 0]]).reshape(-1, 1, 2)
        #         dst = cv2.perspectiveTransform(pts, M)
        #
        #         game_window = cv2.polylines(
        #             game_window,
        #             [np.int32(dst)],
        #             True,
        #             (0, 255, 0),
        #             3,
        #             cv2.LINE_AA
        #         )
    # cv2.imshow('Detected Template', game_window)
    # cv2.waitKey(1)

    # return dst


# Example usage
while True:
    game_window = take_screenshot(HANDLE)
    start = time.time()
    detect_template_orb(game_window, templates)
    # detected_box = detect_template_orb(game_window, templates)
    print(f"{time.time() - start:.4f} seconds")
#     if detected_box is None:
#         continue
#
#     # Draw the detected box on the game window (for visualization)
#     game_window = cv2.polylines(game_window, [np.int32(detected_box)], True, (0, 255, 0), 3,
#                                 cv2.LINE_AA)
#     cv2.imshow('Detected Template', game_window)
#     cv2.waitKey(1)
# cv2.destroyAllWindows()


######OPTICAL FLOW OBJECT TRACKING################
#
# # Load the initial frame and template image
# initial_frame = take_screenshot(HANDLE)
#
# # Convert initial frame to grayscale
# gray_initial_frame = cv2.cvtColor(initial_frame, cv2.COLOR_BGR2GRAY)
#
# # Initialize ORB detector
# orb = cv2.ORB_create()
#
# # Compute keypoints and descriptors for the template
# kp_template, des_template = orb.detectAndCompute(template, None)
#
# # Detect the template in the initial frame using ORB
# kp_initial_frame, des_initial_frame = orb.detectAndCompute(gray_initial_frame, None)
# bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
# matches = bf.match(des_template, des_initial_frame)
# matches = sorted(matches, key=lambda x: x.distance)
#
# # Extract location of good matches
# points_template = np.float32([kp_template[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
# points_initial_frame = np.float32([kp_initial_frame[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
#
# # Use the centroid of matched points as the initial position of the character
# initial_position = np.mean(points_initial_frame, axis=0).astype(np.float32)
#
# # Parameters for Lucas-Kanade optical flow
# lk_params = dict(winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
#
#
# # Initialize previous frame and previous points
# prev_gray = gray_initial_frame
# prev_points = np.array([initial_position])
#
# while True:
#     frame = take_screenshot(HANDLE)
#
#     # Convert current frame to grayscale
#     gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#
#     # Calculate optical flow
#     next_points, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray_frame, prev_points, None, **lk_params)
#
#     # Select good points
#     good_new = next_points[status == 1]
#     good_old = prev_points[status == 1]
#
#     # Draw the tracked points
#     for i, (new, old) in enumerate(zip(good_new, good_old)):
#         a, b = new.ravel()
#         c, d = old.ravel()
#         frame = cv2.circle(frame, (int(a), int(b)), 5, (0, 255, 0), -1)
#
#     # Update previous frame and previous points
#     prev_gray = gray_frame.copy()
#     prev_points = good_new.reshape(-1, 1, 2)
#
#     # Display the frame
#     cv2.imshow('Frame', frame)
#     if cv2.waitKey(30) & 0xFF == ord('q'):
#         break
#
# cv2.destroyAllWindows()
