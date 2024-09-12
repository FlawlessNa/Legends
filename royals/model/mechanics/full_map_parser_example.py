import cv2
import numpy as np
import os
from paths import ROOT
import xml.etree.ElementTree as ET

# Load XML file
tree = ET.parse(os.path.join(ROOT, 'royals/assets/game_files/maps/PathOfTime1.xml'))
root = tree.getroot()

# Find the info & minimap sections
info_section = root.find(".//imgdir[@name='info']")
minimap_section = root.find(".//imgdir[@name='miniMap']")
foothold = root.find(".//imgdir[@name='foothold']")
portals = root.find(".//imgdir[@name='portal']")
ropes = root.find(".//imgdir[@name='ladderRope']")

# Extract VR coordinates
vr_left = int(info_section.find("int[@name='VRLeft']").attrib['value'])
vr_top = int(info_section.find("int[@name='VRTop']").attrib['value'])
vr_right = int(info_section.find("int[@name='VRRight']").attrib['value'])
vr_bottom = int(info_section.find("int[@name='VRBottom']").attrib['value'])
vr_width = vr_right - vr_left
vr_height = vr_bottom - vr_top

minimap_vr_width = int(minimap_section.find("int[@name='width']").attrib['value'])
minimap_vr_height = int(minimap_section.find("int[@name='height']").attrib['value'])
minimap_center_x = int(minimap_section.find("int[@name='centerX']").attrib['value'])
minimap_center_y = int(minimap_section.find("int[@name='centerY']").attrib['value'])

minimap_canvas_width = int(minimap_section.find("canvas[@name='canvas']").attrib['width'])
minimap_canvas_height = int(minimap_section.find("canvas[@name='canvas']").attrib['height'])

vr_scale_x = vr_width / minimap_vr_width
vr_scale_y = vr_height / minimap_vr_height

# Create a blank canvas
canvas = np.zeros((vr_height, vr_width, 4), dtype=np.uint8)

assets = os.path.join(ROOT, 'royals/assets/game_files/maps/images')


# Function to get image path for obj
def get_obj_image_path(oS, l0, l1, l2):
    return os.path.join(assets, oS, f"{l0}.{l1}.{l2}.0.png")


# Function to get image path for tiles
def get_tile_image_path(tS, u, no):
    return os.path.join(assets, tS, f"{u}.{no}.png")


def paste_image(canvas, image, x, y, f, zM, r):
    h, w = image.shape[:2]
    alpha_s = image[:, :, 3] / 255.0
    alpha_l = 1.0 - alpha_s

    # Apply transformations based on f, zM, and r
    if f == 1:
        image = cv2.flip(image, 1)
    # if zM != 1:
    #     image = cv2.resize(image, (0, 0), fx=zM, fy=zM)
    if r != 0:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), r, 1)
        image = cv2.warpAffine(image, M, (w, h))

    x -= w // 2
    y -= h // 2
    x_start = max(x, 0)
    y_start = max(y, 0)
    x_end = min(x + w, vr_width)
    y_end = min(y + h, vr_height)

    image_x_start = x_start - x
    image_y_start = y_start - y
    image_x_end = image_x_start + (x_end - x_start)
    image_y_end = image_y_start + (y_end - y_start)

    for c in range(0, 3):
        # canvas[y:y+h, x:x+w, c] = (alpha_s * image[:, :, c] + alpha_l * canvas[y:y+h, x:x+w, c])
        canvas[y_start:y_end, x_start:x_end, c] = (
                alpha_s[image_y_start:image_y_end, image_x_start:image_x_end] * image[image_y_start:image_y_end, image_x_start:image_x_end, c] +
                alpha_l[image_y_start:image_y_end, image_x_start:image_x_end] * canvas[y_start:y_end, x_start:x_end, c]
        )


# Draw objects
for section in root:
    section_name = section.get('name')
    if section_name.isdigit():
        obj_section = section.find("imgdir[@name='obj']")
        if obj_section is not None:
            for obj in obj_section.findall('imgdir'):
                oS = obj.find("string[@name='oS']").get('value')
                l0 = obj.find("string[@name='l0']").get('value')
                l1 = obj.find("string[@name='l1']").get('value')
                l2 = obj.find("string[@name='l2']").get('value')
                x = int(obj.find("int[@name='x']").get('value')) - vr_left
                y = int(obj.find("int[@name='y']").get('value')) - vr_top
                # if x < 0 or y < 0 or x >= vr_width or y >= vr_height:
                #     breakpoint()
                f = int(obj.find("int[@name='f']").get('value'))
                zM = int(obj.find("int[@name='zM']").get('value'))
                # r = int(obj.find("int[@name='r']").get('value'))
                image_path = get_obj_image_path(oS, l0, l1, l2)
                image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                paste_image(canvas, image, x, y, f, zM, r=0)
                cv2.imshow('image', cv2.resize(canvas, None, fx=0.5, fy=0.5))
                cv2.waitKey(1)

# Draw tiles
for section in root:
    section_name = section.get('name')
    if section_name.isdigit():
        tile_section = section.find("imgdir[@name='tile']")
        if tile_section is not None:
            for tile in tile_section.findall('imgdir'):
                info_section = section.find("imgdir[@name='info']")
                tS = info_section.find("string[@name='tS']").get('value')
                u = tile.find("string[@name='u']").get('value')
                no = tile.find("int[@name='no']").get('value')
                x = int(tile.find("int[@name='x']").get('value')) - vr_left
                y = int(tile.find("int[@name='y']").get('value')) - vr_top
                zM = int(tile.find("int[@name='zM']").get('value'))
                image_path = get_tile_image_path(tS, u, no)
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
                    # pass
                # if x < 0 or y < 0 or x >= vr_width or y >= vr_height:
                #     breakpoint()
                paste_image(canvas, image, x, y, f=0, zM=zM, r=0)
                cv2.imshow('image', cv2.resize(canvas, None, fx=0.5, fy=0.5))
                cv2.waitKey(1)


def extract_coordinates(element, coordinates, attribs: list[str]):
    # Check if the element contains x1, y1, x2, and y2 attributes
    extraction = {}
    for attrib in attribs:
        extraction[attrib] = element.find(f"int[@name='{attrib}']")
    # x1 = element.find("int[@name='x1']")
    # y1 = element.find("int[@name='y1']")
    # x2 = element.find("int[@name='x2']")
    # y2 = element.find("int[@name='y2']")

    if all(elem is not None for elem in extraction.values()):
        # Extract the coordinates and add them to the list
        coordinates.append(
            {
                **{k: int(v.get('value')) for k, v in extraction.items()},
                'name': element.attrib['name']
            }
        )


    # Recursively call the function for each child element
    for child in element:
        extract_coordinates(child, coordinates, attribs)


def minimap_to_vr(x, y):
    return int(x * vr_scale_x - vr_left), int(y * vr_scale_y - vr_top)


# canvas = cv2.resize(canvas, (minimap_vr_width, minimap_vr_height))

fh_coords = []
extract_coordinates(foothold, fh_coords, ['x1', 'y1', 'x2', 'y2', 'prev', 'next'])

for coord in fh_coords:
    # x1, y1 = coord['x1'] + minimap_center_x, coord['y1'] + minimap_center_y
    # x2, y2 = coord['x2'] + minimap_center_x, coord['y2'] + minimap_center_y
    # x1, y1 = minimap_to_vr(x1, y1)
    # x2, y2 = minimap_to_vr(x2, y2)
    x1, y1 = coord['x1'] - vr_left, coord['y1'] - vr_top
    x2, y2 = coord['x2'] - vr_left, coord['y2'] - vr_top
    if x1 > canvas.shape[1] or x2 > canvas.shape[1] or y1 > canvas.shape[0] or y2 > canvas.shape[0]:
        breakpoint()
    elif x1 < 0 or x2 < 0 or y1 < 0 or y2 < 0:
        breakpoint()
    prev = coord['prev']
    next = coord['next']
    cv2.line(canvas, (x1, y1), (x2, y2), (255, 255, 255), 3)
    cv2.imshow('Canvas', cv2.resize(canvas, None, fx=0.5, fy=0.5))
    cv2.waitKey(1)
    print('Name:', coord['name'], 'Prev:', prev, 'Next:', next)
portals_coords = []
extract_coordinates(portals, portals_coords, ['x', 'y'])

for coord in portals_coords:
    print(coord)
    # x, y = coord['x'] + minimap_center_x, coord['y'] + minimap_center_y
    x, y = coord['x'] - vr_left, coord['y'] - vr_top
    cv2.circle(canvas, (x, y), 1, (0, 255, 0), 15)
    cv2.imshow('Canvas', cv2.resize(canvas, None, fx=0.5, fy=0.5))
    # cv2.imshow('Canvas', canvas)
    cv2.waitKey(1)

rope_coords = []
extract_coordinates(ropes, rope_coords, ['x', 'y1', 'y2'])

for coord in rope_coords:
    # x, y1 = coord['x'] + minimap_center_x, coord['y1'] + minimap_center_y
    # x, y2 = coord['x'] + minimap_center_x, coord['y2'] + minimap_center_y
    x, y1 = coord['x'] - vr_left, coord['y1'] - vr_top
    x, y2 = coord['x'] - vr_left, coord['y2'] - vr_top
    cv2.line(canvas, (x, y1), (x, y2), (0, 0, 255), 5)
cv2.imshow('Canvas', cv2.resize(canvas, None, fx=0.5, fy=0.5))
# cv2.imshow('Canvas', canvas)
cv2.waitKey(1)
breakpoint()