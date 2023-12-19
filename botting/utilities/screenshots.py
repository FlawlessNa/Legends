import cv2
import numpy as np
import win32con
import win32gui
import win32ui

from .box import Box

CLIENT_HORIZONTAL_MARGIN_PX = 3
CLIENT_VERTICAL_MARGIN_PX = 29


def take_screenshot(
    handle: int | None = None,
    dimensions: dict | None | Box = None,
) -> np.ndarray:
    """
    Function takes a rapid screenshot of the window associated with handle parameter.
    If dimensions are provided, it takes only a screenshot of that region.
    If no handle is given, it takes a screenshot of the entire main screen.
    Returns the image taken as a numpy array.

    :param handle: Integer representing the handle to the window being screenshot-ed.
     If None provided, the entire screen is captured instead.
    :param dimensions: Coord. within the window -relative to window position,
     or within screen if no window- to be recorded.
     Dictionary must have top, left, right, bottom keys.
    :return: a numpy array representing the image captured.
    """
    if not handle:
        handle = win32gui.GetDesktopWindow()

    if dimensions:
        left = dimensions["left"]
        top = dimensions["top"]
        right = dimensions["right"]
        bottom = dimensions["bottom"]
    else:
        # Offsetting by 30 pixel to remove titlebar from screenshots
        left, top, right, bottom = win32gui.GetClientRect(handle)
        left += CLIENT_HORIZONTAL_MARGIN_PX
        right += CLIENT_HORIZONTAL_MARGIN_PX
        top += CLIENT_VERTICAL_MARGIN_PX
        bottom += CLIENT_VERTICAL_MARGIN_PX

    width = int(right - left)
    height = int(bottom - top)
    # while True:
    #     try:
    window_dc = win32gui.GetWindowDC(handle)
    dc_object = win32ui.CreateDCFromHandle(window_dc)
    compatible_dc = dc_object.CreateCompatibleDC()
    data_bit_map = win32ui.CreateBitmap()
    data_bit_map.CreateCompatibleBitmap(dc_object, width, height)
    compatible_dc.SelectObject(data_bit_map)
    compatible_dc.BitBlt(
        (0, 0), (width, height), dc_object, (left, top), win32con.SRCCOPY
    )
    signed_integers_array = data_bit_map.GetBitmapBits(True)
    dc_object.DeleteDC()
    compatible_dc.DeleteDC()
    win32gui.ReleaseDC(handle, window_dc)
    win32gui.DeleteObject(data_bit_map.GetHandle())
    #     break
    #
    # except win32ui.error:
    #     logger.info(
    #         f"Error in taking screenshot. Trying again. Dimensions parameter is {dimensions}"
    #     )
    #     time.sleep(1)

    img = np.fromstring(signed_integers_array, dtype="uint8")
    img.shape = (height, width, 4)

    img = img[:, :, :3]
    img = np.ascontiguousarray(img)

    # if mask is not None:
    #     img = cv2.bitwise_and(img, img, mask=mask)

    return img


def find_image(
    haystack: np.ndarray,
    needle: np.ndarray,
    method: int = cv2.TM_CCORR_NORMED,
    threshold: float = 0.99,
    add_margins: bool = True,
) -> list[Box]:
    """
    Find an image within another image.
    :param haystack: The image to search in.
    :param needle: The image to search for.
    :param method: The method to use for finding the image. See https://docs.opencv.org/4.5.2/d4/dc6/tutorial_py_template_matching.html
    :param threshold: The threshold to use for finding the image. See https://docs.opencv.org/4.5.2/d4/dc6/tutorial_py_template_matching.html
    :param add_margins: Whether to add client horizontal/vertical margins to the found boxes or not. Default True.
    :return: A list of boxes (regions) where the needle image was found.
    """
    result = cv2.matchTemplate(haystack, needle, method)
    locations = np.where(result >= threshold)
    locations = zip(*locations[::-1])

    rectangles = list()
    for loc in locations:
        rect = [int(loc[0]), int(loc[1]), needle.shape[1], needle.shape[0]]
        rectangles.append(rect)
        rectangles.append(rect)

    rectangles, weights = cv2.groupRectangles(rectangles, groupThreshold=1, eps=0.5)
    if add_margins:
        return [
            Box(
                left=r.tolist()[0] + CLIENT_HORIZONTAL_MARGIN_PX,
                top=r.tolist()[1] + CLIENT_VERTICAL_MARGIN_PX,
                right=r.tolist()[0] + r.tolist()[2] + CLIENT_HORIZONTAL_MARGIN_PX,
                bottom=r.tolist()[1] + r.tolist()[3] + CLIENT_VERTICAL_MARGIN_PX,
            )
            for r in rectangles
        ]
    else:
        return [
            Box(
                left=r.tolist()[0],
                top=r.tolist()[1],
                right=r.tolist()[0] + r.tolist()[2],
                bottom=r.tolist()[1] + r.tolist()[3],
            )
            for r in rectangles
        ]
