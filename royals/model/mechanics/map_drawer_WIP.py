import cv2
import numpy as np
import os
from paths import ROOT
import xml.etree.ElementTree as ET

# Load XML file
tree = ET.parse(os.path.join(ROOT, 'royals/assets/game_files/maps/UluEstate2.xml'))
root = tree.getroot()

# Find the info section
info_section = root.find(".//imgdir[@name='info']")

# Extract VR coordinates
vr_left = int(info_section.find("int[@name='VRLeft']").attrib['value'])
vr_top = int(info_section.find("int[@name='VRTop']").attrib['value'])
vr_right = int(info_section.find("int[@name='VRRight']").attrib['value'])
vr_bottom = int(info_section.find("int[@name='VRBottom']").attrib['value'])

# Calculate width and height
width = vr_right - vr_left
height = vr_bottom - vr_top

# Create a blank canvas
canvas = np.zeros((height, width, 4), dtype=np.uint8)

assets = os.path.join(ROOT, 'royals/assets/game_files/maps/images')

# Function to get image path for obj
def get_obj_image_path(oS, l0, l1, l2):
    return os.path.join(assets, oS, f"{l0}.{l1}.{l2}.0.png")

# Function to get image path for tiles
def get_tile_image_path(u, no):
    return os.path.join(assets, "jungleSG", f"{u}.{no}.png")

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
    for c in range(0, 3):
        canvas[y:y+h, x:x+w, c] = (alpha_s * image[:, :, c] + alpha_l * canvas[y:y+h, x:x+w, c])

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
                x = int(obj.find("int[@name='x']").get('value')) + vr_left
                y = int(obj.find("int[@name='y']").get('value')) + vr_top
                f = int(obj.find("int[@name='f']").get('value'))
                zM = int(obj.find("int[@name='zM']").get('value'))
                r = int(obj.find("int[@name='r']").get('value'))
                image_path = get_obj_image_path(oS, l0, l1, l2)
                image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                paste_image(canvas, image, x, y, f, zM, r)
                cv2.imshow('image', canvas)
                cv2.waitKey(1)

# Draw tiles
for section in root.findall(".//imgdir[@name]"):
    section_name = section.get('name')
    if section_name.isdigit() and int(section_name) in range(8):
        for tile in section.findall(".//imgdir[@name='tiles']"):
            for tile_section in tile.findall(".//imgdir"):
                u = tile_section.find("int[@name='u']").get('value')
                no = tile_section.find("int[@name='no']").get('value')
                x = int(tile_section.find("int[@name='x']").get('value'))
                y = int(tile_section.find("int[@name='y']").get('value'))
                image_path = get_tile_image_path(u, no)
                image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                paste_image(canvas, image, x, y)
                cv2.imshow('image', canvas)
                cv2.waitKey(0)
