import cv2
import numpy as np
import os
from paths import ROOT
import xml.etree.ElementTree as ET

from royals import royals_ign_finder
from royals.model.interface.dynamic_components.minimap import Minimap
from botting.utilities import client_handler

# Strategy:
# 1. Draw on the Minimap Canvas
# 2. Extract character position on minimap, translate into minimap VR coordinates
# 3. subtract minimap_centers to this, then subtract actual VR coordinates
# 4. Draw result on VR canvas

class MapParser:
    _ASSETS = os.path.join(ROOT, 'royals/assets/game_files/maps')

    def __init__(self, map_name: str):
        self.tree = ET.parse(os.path.join(self._ASSETS, f'{map_name}.xml'))
        self.root = self.tree.getroot()

        self._info_section = self.root.find(".//imgdir[@name='info']")
        self._minimap_section = self.root.find(".//imgdir[@name='miniMap']")
        self._foothold = self.root.find(".//imgdir[@name='foothold']")
        self._portals = self.root.find(".//imgdir[@name='portal']")
        self._ropes = self.root.find(".//imgdir[@name='ladderRope']")

        # Extract VR coordinates
        self.vr_left = int(self._info_section.find("int[@name='VRLeft']").attrib['value'])
        self.vr_top = int(self._info_section.find("int[@name='VRTop']").attrib['value'])
        self.vr_right = int(self._info_section.find("int[@name='VRRight']").attrib['value'])
        self.vr_bottom = int(self._info_section.find("int[@name='VRBottom']").attrib['value'])
        self.vr_width = self.vr_right - self.vr_left
        self.vr_height = self.vr_bottom - self.vr_top

        # Extract minimap section
        self.minimap_vr_width = int(self._minimap_section.find("int[@name='width']").attrib['value'])
        self.minimap_vr_height = int(self._minimap_section.find("int[@name='height']").attrib['value'])
        self.minimap_center_x = int(self._minimap_section.find("int[@name='centerX']").attrib['value'])
        self.minimap_center_y = int(self._minimap_section.find("int[@name='centerY']").attrib['value'])

        self.minimap_canvas_width = int(self._minimap_section.find("canvas[@name='canvas']").attrib['width'])
        self.minimap_canvas_height = int(self._minimap_section.find("canvas[@name='canvas']").attrib['height'])

        self.vr_canvas = np.zeros((self.vr_height, self.vr_width, 4), dtype=np.uint8)
        self.minimap_canvas = np.zeros((self.minimap_vr_height, self.minimap_vr_width, 3), dtype=np.uint8)
        self.minimap_scale_x = self.minimap_vr_width / self.minimap_canvas_width
        self.minimap_scale_y = self.minimap_vr_height / self.minimap_canvas_height

    def draw_vr_canvas(self):
        self._draw_objs()
        self._draw_tiles()
        self._draw_footholds()
        self._draw_portals()
        self._draw_ropes()

    @staticmethod
    def get_obj_image_path(oS, l0, l1, l2):
        return os.path.join(MapParser._ASSETS, 'images', oS, f"{l0}.{l1}.{l2}.0.png")

    @staticmethod
    def get_tile_image_path(tS, u, no):
        return os.path.join(MapParser._ASSETS, 'images', tS, f"{u}.{no}.png")

    def paste_image(self, canvas, image, x, y, f, zM, r):
        h, w = image.shape[:2]
        alpha_s = image[:, :, 3] / 255.0
        alpha_l = 1.0 - alpha_s

        if f == 1:
            image = cv2.flip(image, 1)
        x -= w // 2
        y -= h // 2
        x_start = max(x, 0)
        y_start = max(y, 0)
        x_end = min(x + w, self.vr_width)
        y_end = min(y + h, self.vr_height)

        image_x_start = x_start - x
        image_y_start = y_start - y
        image_x_end = image_x_start + (x_end - x_start)
        image_y_end = image_y_start + (y_end - y_start)

        for c in range(0, 3):
            canvas[y_start:y_end, x_start:x_end, c] = (
                alpha_s[image_y_start:image_y_end, image_x_start:image_x_end] * image[
                                                                                image_y_start:image_y_end,
                                                                                image_x_start:image_x_end,
                                                                                c] +
                alpha_l[image_y_start:image_y_end, image_x_start:image_x_end] * canvas[
                                                                                y_start:y_end,
                                                                                x_start:x_end,
                                                                                c]
            )

    def _draw_objs(self):
        for section in self.root:
            section_name = section.get('name')
            if section_name.isdigit():
                obj_section = section.find("imgdir[@name='obj']")
                if obj_section is not None:
                    for obj in obj_section.findall('imgdir'):
                        oS = obj.find("string[@name='oS']").get('value')
                        l0 = obj.find("string[@name='l0']").get('value')
                        l1 = obj.find("string[@name='l1']").get('value')
                        l2 = obj.find("string[@name='l2']").get('value')
                        x = int(obj.find("int[@name='x']").get('value')) - self.vr_left
                        y = int(obj.find("int[@name='y']").get('value')) - self.vr_top
                        f = int(obj.find("int[@name='f']").get('value'))
                        zM = int(obj.find("int[@name='zM']").get('value'))
                        image_path = self.get_obj_image_path(oS, l0, l1, l2)
                        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                        self.paste_image(self.vr_canvas, image, x, y, f, zM, r=0)


    def _draw_tiles(self):
        for section in self.root:
            section_name = section.get('name')
            if section_name.isdigit():
                tile_section = section.find("imgdir[@name='tile']")
                if tile_section is not None:
                    for tile in tile_section.findall('imgdir'):
                        info_section = section.find("imgdir[@name='info']")
                        tS = info_section.find("string[@name='tS']").get('value')
                        u = tile.find("string[@name='u']").get('value')
                        no = tile.find("int[@name='no']").get('value')
                        x = int(tile.find("int[@name='x']").get('value')) - self.vr_left
                        y = int(tile.find("int[@name='y']").get('value')) - self.vr_top
                        zM = int(tile.find("int[@name='zM']").get('value'))
                        image_path = self.get_tile_image_path(tS, u, no)
                        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                        h, w = image.shape[:2]
                        if u == 'enH0':
                            x += w // 2
                            y -= h // 2
                        elif u == 'bsc':
                            x += w // 2
                            y += h // 2
                        elif u == 'enH1':
                            x += w // 2
                            y += h // 2
                        elif u == 'edD':
                            y += h // 2
                        elif u == 'edU':
                            y -= h // 2
                        elif u == 'enV0':
                            x -= w // 2
                            y += h // 2
                        elif u == 'enV1':
                            x += w // 2
                            y += h // 2
                        elif u == 'slLD':
                            x -= w // 2
                            y += h // 2
                            pass
                        elif u == 'slLU':
                            breakpoint()
                        elif u == 'slRD':
                            x += w // 2
                            y += h // 2

                        elif u == 'slRU':
                            breakpoint()

                        else:
                            breakpoint()
                        self.paste_image(self.vr_canvas, image, x, y, f=0, zM=zM, r=0)

    @staticmethod
    def _extract_coordinates(element, attribs: list[str]):
        # Check if the element contains x1, y1, x2, and y2 attributes
        result = []

        def _recursive_extract(element, extraction, attribs):
            for attrib in attribs:
                extraction[attrib] = element.find(f"int[@name='{attrib}']")
            if all(elem is not None for elem in extraction.values()):
                result.append(
                    {
                        **{k: int(v.get('value')) for k, v in extraction.items()},
                        'name': element.attrib['name']
                    }
                )
            for child in element:
                _recursive_extract(child, extraction, attribs)


        _recursive_extract(element, {}, attribs)
        return result

    def _draw_footholds(self):
        fh_coords = self._extract_coordinates(self._foothold, ['x1', 'y1', 'x2', 'y2'])
        for coord in fh_coords:
            x1, y1 = coord['x1'] - self.vr_left, coord['y1'] - self.vr_top
            x2, y2 = coord['x2'] - self.vr_left, coord['y2'] - self.vr_top
            if x1 > self.vr_canvas.shape[1] or x2 > self.vr_canvas.shape[1] or y1 > self.vr_canvas.shape[
                0] or y2 > self.vr_canvas.shape[0]:
                breakpoint()
            elif x1 < 0 or x2 < 0 or y1 < 0 or y2 < 0:
                breakpoint()
            cv2.line(self.vr_canvas, (x1, y1), (x2, y2), (255, 255, 255), 3)


    def _draw_portals(self):
        portal_coords = self._extract_coordinates(self._portals, ['x', 'y'])
        for coord in portal_coords:
            x, y = coord['x'] - self.vr_left, coord['y'] - self.vr_top
            cv2.circle(self.vr_canvas, (x, y), 1, (0, 255, 0), 5)

    def _draw_ropes(self):
        rope_coords = self._extract_coordinates(self._ropes, ['x', 'y1', 'y2'])
        for coord in rope_coords:
            x, y1, y2 = coord['x'] - self.vr_left, coord['y1'] - self.vr_top, coord['y2'] - self.vr_top
            cv2.line(self.vr_canvas, (x, y1), (x, y2), (0, 0, 255), 3)

    def translate_to_vr(self, pos):
        x, y = pos
        scaled_x, scaled_y = x * self.minimap_scale_x, y * self.minimap_scale_y
        x = int(scaled_x - self.minimap_center_x - self.vr_left)
        y = int(scaled_y - self.minimap_scale_y - self.vr_top)
        return x, y


if __name__ == '__main__':
    map_name = 'PathOfTime1'
    map_parser = MapParser(map_name)
    map_parser.draw_vr_canvas()
    HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)


    class FakeMinimap(Minimap):
        map_area_width = map_parser.minimap_canvas_width
        map_area_height = map_parser.minimap_canvas_height

        def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
            pass

    minimap = FakeMinimap()
    map_area_box = minimap.get_map_area_box(HANDLE)
    while True:
        copied = map_parser.vr_canvas.copy()
        pos = minimap.get_character_positions(HANDLE).pop()
        pos = map_parser.translate_to_vr(pos)
        cv2.circle(copied, pos, 1, (0, 255, 0), 3)
        cv2.imshow('Canvas', cv2.resize(copied, None, fx=0.5, fy=0.5))
        cv2.waitKey(1)

# import cv2
# import numpy as np
#
# # Load the template image (object/tile)
# template = cv2.imread('path_to_template_image.png', cv2.IMREAD_GRAYSCALE)
# template_height, template_width = template.shape[:2]
#
# # Initialize ORB detector
# orb = cv2.ORB_create()
#
# # Compute keypoints and descriptors for the template
# kp_template, des_template = orb.detectAndCompute(template, None)
#
#
# # Function to detect the template in the game window using ORB
# def detect_template_orb(game_window):
#     # Convert game window to grayscale
#     gray_window = cv2.cvtColor(game_window, cv2.COLOR_BGR2GRAY)
#
#     # Compute keypoints and descriptors for the game window
#     kp_window, des_window = orb.detectAndCompute(gray_window, None)
#
#     # Match descriptors using BFMatcher
#     bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
#     matches = bf.match(des_template, des_window)
#
#     # Sort matches by distance
#     matches = sorted(matches, key=lambda x: x.distance)
#
#     # Draw matches (for visualization)
#     result = cv2.drawMatches(template, kp_template, game_window, kp_window,
#                              matches[:10], None,
#                              flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
#
#     # Extract location of good matches
#     points_template = np.float32([kp_template[m.queryIdx].pt for m in matches]).reshape(
#         -1, 1, 2)
#     points_window = np.float32([kp_window[m.trainIdx].pt for m in matches]).reshape(-1,
#                                                                                     1,
#                                                                                     2)
#
#     # Find homography
#     M, mask = cv2.findHomography(points_template, points_window, cv2.RANSAC, 5.0)
#
#     # Use homography to find the bounding box of the detected template
#     h, w = template.shape
#     pts = np.float32([[0, 0], [0, h], [w, h], [w, 0]]).reshape(-1, 1, 2)
#     dst = cv2.perspectiveTransform(pts, M)
#
#     return dst
#
#
# # Example usage
# game_window = cv2.imread('path_to_game_window_image.png')
# detected_box = detect_template_orb(game_window)
#
# # Draw the detected box on the game window (for visualization)
# game_window = cv2.polylines(game_window, [np.int32(detected_box)], True, (0, 255, 0), 3,
#                             cv2.LINE_AA)
# cv2.imshow('Detected Template', game_window)
# cv2.waitKey(0)
# cv2.destroyAllWindows()



######################
# import cv2
# import numpy as np
#
# # Load the initial frame and template image
# initial_frame = cv2.imread('path_to_initial_frame.png')
# template = cv2.imread('path_to_template_image.png', cv2.IMREAD_GRAYSCALE)
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
# # Capture video or continuous frames
# cap = cv2.VideoCapture('path_to_video_or_camera')
#
# # Initialize previous frame and previous points
# prev_gray = gray_initial_frame
# prev_points = np.array([initial_position])
#
# while cap.isOpened():
#     ret, frame = cap.read()
#     if not ret:
#         break
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
#         frame = cv2.circle(frame, (a, b), 5, (0, 255, 0), -1)
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
# cap.release()
# cv2.destroyAllWindows()