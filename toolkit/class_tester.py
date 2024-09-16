import asyncio
import cv2
import os
import numpy as np
import win32gui
from botting import controller
from botting.utilities import client_handler, Box, take_screenshot, find_image
from royals import royals_ign_finder
from paths import ROOT
from royals.model.minimaps import KampungVillageMinimap, FantasyThemePark1Minimap

from royals.model.characters import Bishop
from royals.model.mechanics.movement_mechanics import Movements
from royals.actions.skills_related_v2 import cast_skill
from royals.actions.movements_v2 import telecast

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
img_dir = os.path.join(ROOT, "royals/assets/detection_images")

if __name__ == "__main__":
    door_img = cv2.imread(os.path.join(img_dir, "ActiveDoor.png"), cv2.IMREAD_GRAYSCALE)
    door_frame_img = cv2.imread(
        os.path.join(img_dir, "ActiveDoorFrame.png"), cv2.IMREAD_GRAYSCALE
    )
    mask_frame = np.ones(door_frame_img.shape, dtype=np.uint8)
    mask_frame[door_frame_img == 0] = 0
    masked_door_frame = cv2.bitwise_and(door_frame_img, door_frame_img, mask=mask_frame)
    # breakpoint()
    while True:
        client_img = take_screenshot(HANDLE)
        # orb = cv2.ORB_create()
        #
        # # Detect keypoints and compute descriptors
        # keypoints1, descriptors1 = orb.detectAndCompute(door_img, None)
        # keypoints2, descriptors2 = orb.detectAndCompute(client_img, None)
        #
        # # Use BFMatcher to match descriptors
        # bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        # matches = bf.match(descriptors1, descriptors2)
        #
        # # Sort matches by distance
        # matches = sorted(matches, key=lambda x: x.distance)
        #
        # # Draw the top matches
        # needle_img_matches = cv2.drawMatches(door_img, keypoints1, client_img,
        #                                      keypoints2, matches[:10], None,
        #                                      flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        #
        # # Find the homography
        # if len(matches) > 4:
        #     src_pts = np.float32([keypoints1[m.queryIdx].pt for m in matches]).reshape(
        #         -1, 1, 2)
        #     dst_pts = np.float32([keypoints2[m.trainIdx].pt for m in matches]).reshape(
        #         -1, 1, 2)
        #     M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        #     h, w = door_img.shape
        #     pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(
        #         -1, 1, 2)
        #     dst = cv2.perspectiveTransform(pts, M)
        #     client_img = cv2.polylines(client_img, [np.int32(dst)], True, 255, 3,
        #                                  cv2.LINE_AA)
        #
        # # Display the result
        # cv2.imshow('Matches', needle_img_matches)
        # cv2.imshow('Detected', client_img)
        # cv2.waitKey(1)
        gray = cv2.cvtColor(client_img, cv2.COLOR_BGR2GRAY)
        frame_res = cv2.matchTemplate(
            gray, door_frame_img, cv2.TM_CCOEFF_NORMED, mask=mask_frame
        )
        door_res = cv2.matchTemplate(gray, door_img, cv2.TM_CCOEFF_NORMED)

        _, max_frame_val, _, max_frame_loc = cv2.minMaxLoc(frame_res)
        _, max_door_val, _, max_door_loc = cv2.minMaxLoc(door_res)

        print("Frame", max_frame_val)
        print("Door", max_door_val)

        # Draw the rectangles
        cv2.rectangle(
            client_img,
            max_frame_loc,
            (
                max_frame_loc[0] + door_frame_img.shape[1],
                max_frame_loc[1] + door_frame_img.shape[0],
            ),
            (255, 0, 0),
            2,
        )
        cv2.rectangle(
            client_img,
            max_door_loc,
            (max_door_loc[0] + door_img.shape[1], max_door_loc[1] + door_img.shape[0]),
            (0, 0, 255),
            2,
        )
        cv2.imshow("Client", client_img)
        cv2.waitKey(1)
