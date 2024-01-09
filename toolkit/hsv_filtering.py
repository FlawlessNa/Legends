import cv2
import numpy as np

from botting.utilities import take_screenshot


def init_control_gui_hsv():
    """
    Initialize the trackbars that will control the filters.
    :return:
    """

    cv2.namedWindow("Trackbars HSV", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Trackbars HSV", 350, 700)

    # required callback. we'll be using getTrackbarPos() to do lookups
    # instead of using the callback.
    def nothing(position):
        pass

    # create trackbars for bracketing.
    # OpenCV scale for HSV is H: 0-179, S: 0-255, V: 0-255
    cv2.createTrackbar("HMin", "Trackbars HSV", 0, 179, nothing)
    cv2.createTrackbar("SMin", "Trackbars HSV", 0, 255, nothing)
    cv2.createTrackbar("VMin", "Trackbars HSV", 0, 255, nothing)
    cv2.createTrackbar("HMax", "Trackbars HSV", 0, 179, nothing)
    cv2.createTrackbar("SMax", "Trackbars HSV", 0, 255, nothing)
    cv2.createTrackbar("VMax", "Trackbars HSV", 0, 255, nothing)
    # Set default value for Max HSV trackbars
    cv2.setTrackbarPos("HMax", "Trackbars HSV", 179)
    cv2.setTrackbarPos("SMax", "Trackbars HSV", 255)
    cv2.setTrackbarPos("VMax", "Trackbars HSV", 255)

    # trackbars for increasing/decreasing saturation and value
    cv2.createTrackbar("SAdd", "Trackbars HSV", 0, 255, nothing)
    cv2.createTrackbar("SSub", "Trackbars HSV", 0, 255, nothing)
    cv2.createTrackbar("VAdd", "Trackbars HSV", 0, 255, nothing)
    cv2.createTrackbar("VSub", "Trackbars HSV", 0, 255, nothing)

    cv2.createTrackbar("Threshold1", "Trackbars HSV", 0, 1000, nothing)
    cv2.createTrackbar("Threshold2", "Trackbars HSV", 0, 1000, nothing)
    cv2.createTrackbar("Apply Canny", "Trackbars HSV", 0, 1, nothing)

    cv2.createTrackbar("groupThresh", "Trackbars HSV", 1, 100, nothing)
    cv2.createTrackbar("Eps", "Trackbars HSV", 0, 100, nothing)
    cv2.createTrackbar("minWidth", "Trackbars HSV", 0, 100, nothing)
    cv2.createTrackbar("minHeight", "Trackbars HSV", 0, 100, nothing)


def init_control_gui_color():
    """
    Initialize the trackbars that will control the filters.
    :return:
    """

    cv2.namedWindow("Trackbars Color", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Trackbars Color", 350, 700)

    # required callback. we'll be using getTrackbarPos() to do lookups
    # instead of using the callback.
    def nothing(position):
        pass

    # create trackbars for bracketing.
    # OpenCV scale for HSV is H: 0-179, S: 0-255, V: 0-255
    cv2.createTrackbar("BMin", "Trackbars Color", 0, 255, nothing)
    cv2.createTrackbar("GMin", "Trackbars Color", 0, 255, nothing)
    cv2.createTrackbar("RMin", "Trackbars Color", 0, 255, nothing)
    cv2.createTrackbar("BMax", "Trackbars Color", 0, 255, nothing)
    cv2.createTrackbar("GMax", "Trackbars Color", 0, 255, nothing)
    cv2.createTrackbar("RMax", "Trackbars Color", 0, 255, nothing)
    cv2.createTrackbar("groupThresh", "Trackbars Color", 1, 100, nothing)
    cv2.createTrackbar("Eps", "Trackbars Color", 0, 100, nothing)
    cv2.createTrackbar("minWidth", "Trackbars Color", 0, 100, nothing)
    cv2.createTrackbar("minHeight", "Trackbars Color", 0, 100, nothing)
    cv2.createTrackbar("maxWidth", "Trackbars Color", 0, 1000, nothing)
    cv2.createTrackbar("maxHeight", "Trackbars Color", 0, 1000, nothing)
    # Set default value for Max HSV trackbars
    cv2.setTrackbarPos("BMax", "Trackbars Color", 255)
    cv2.setTrackbarPos("GMax", "Trackbars Color", 255)
    cv2.setTrackbarPos("RMax", "Trackbars Color", 255)
    cv2.setTrackbarPos("maxWidth", "Trackbars Color", 1000)
    cv2.setTrackbarPos("maxHeight", "Trackbars Color", 1000)


def get_hsv_filter_from_controls():
    # Get current positions of all trackbars
    hsv_filter = HsvFilter()
    hsv_filter.hMin = cv2.getTrackbarPos("HMin", "Trackbars HSV")
    hsv_filter.sMin = cv2.getTrackbarPos("SMin", "Trackbars HSV")
    hsv_filter.vMin = cv2.getTrackbarPos("VMin", "Trackbars HSV")
    hsv_filter.hMax = cv2.getTrackbarPos("HMax", "Trackbars HSV")
    hsv_filter.sMax = cv2.getTrackbarPos("SMax", "Trackbars HSV")
    hsv_filter.vMax = cv2.getTrackbarPos("VMax", "Trackbars HSV")
    hsv_filter.sAdd = cv2.getTrackbarPos("SAdd", "Trackbars HSV")
    hsv_filter.sSub = cv2.getTrackbarPos("SSub", "Trackbars HSV")
    hsv_filter.vAdd = cv2.getTrackbarPos("VAdd", "Trackbars HSV")
    hsv_filter.vSub = cv2.getTrackbarPos("VSub", "Trackbars HSV")
    hsv_filter.groupthresh = cv2.getTrackbarPos("groupThresh", "Trackbars HSV")
    hsv_filter.eps = cv2.getTrackbarPos("Eps", "Trackbars HSV") / 10
    hsv_filter.w = cv2.getTrackbarPos("minWidth", "Trackbars HSV")
    hsv_filter.h = cv2.getTrackbarPos("minHeight", "Trackbars HSV")
    return hsv_filter


def get_colors_filter_from_controls():
    # Get current positions of all trackbars
    colors_filter = ColorsFilter()
    colors_filter.bMin = cv2.getTrackbarPos("BMin", "Trackbars Color")
    colors_filter.gMin = cv2.getTrackbarPos("GMin", "Trackbars Color")
    colors_filter.rMin = cv2.getTrackbarPos("RMin", "Trackbars Color")
    colors_filter.bMax = cv2.getTrackbarPos("BMax", "Trackbars Color")
    colors_filter.gMax = cv2.getTrackbarPos("GMax", "Trackbars Color")
    colors_filter.rMax = cv2.getTrackbarPos("RMax", "Trackbars Color")
    colors_filter.eps = cv2.getTrackbarPos("Eps", "Trackbars Color") / 10
    colors_filter.groupthresh = cv2.getTrackbarPos("groupThresh", "Trackbars Color")
    colors_filter.minw = cv2.getTrackbarPos("minWidth", "Trackbars Color")
    colors_filter.minh = cv2.getTrackbarPos("minHeight", "Trackbars Color")
    colors_filter.maxw = cv2.getTrackbarPos("maxWidth", "Trackbars Color")
    colors_filter.maxh = cv2.getTrackbarPos("maxHeight", "Trackbars Color")
    return colors_filter


def get_canny_filter_from_controls():
    if cv2.getTrackbarPos("Apply Canny", "Trackbars HSV") == 1:
        return (
            cv2.getTrackbarPos("Threshold1", "Trackbars HSV"),
            cv2.getTrackbarPos("Threshold2", "Trackbars HSV"),
        )


# given an image and an HSV filter, apply the filter and return the resulting image.
# if a filter is not supplied, the control GUI trackbars will be used
def apply_hsv_filters(original_image, hsv_filter=None, canny_filter=None):
    # convert image to HSV
    hsv = cv2.cvtColor(original_image, cv2.COLOR_BGR2HSV)

    # if we haven't been given a defined filter, use the filter values from the GUI
    if not hsv_filter:
        hsv_filter = get_hsv_filter_from_controls()

    if not canny_filter:
        canny_filter = get_canny_filter_from_controls()

    # add/subtract saturation and value
    h, s, v = cv2.split(hsv)
    s = shift_channel(s, hsv_filter.sAdd)
    s = shift_channel(s, -hsv_filter.sSub)
    v = shift_channel(v, hsv_filter.vAdd)
    v = shift_channel(v, -hsv_filter.vSub)
    hsv = cv2.merge([h, s, v])

    # Set minimum and maximum HSV values to display
    lower = np.array([hsv_filter.hMin, hsv_filter.sMin, hsv_filter.vMin])
    upper = np.array([hsv_filter.hMax, hsv_filter.sMax, hsv_filter.vMax])
    # Apply the thresholds
    mask = cv2.inRange(hsv, lower, upper)
    result = cv2.bitwise_and(hsv, hsv, mask=mask)

    # convert back to BGR for imshow() to display it properly
    img = cv2.cvtColor(result, cv2.COLOR_HSV2BGR)

    if canny_filter is not None:
        img = cv2.Canny(img, *canny_filter, L2gradient=True)

    return img


# given an image and an HSV filter, apply the filter and return the resulting image.
# if a filter is not supplied, the control GUI trackbars will be used
def apply_color_filters(original_image, color_filter=None):
    # if we haven't been given a defined filter, use the filter values from the GUI
    if not color_filter:
        color_filter = get_colors_filter_from_controls()

    # Set minimum and maximum HSV values to display
    lower = np.array([color_filter.bMin, color_filter.gMin, color_filter.rMin])
    upper = np.array([color_filter.bMax, color_filter.gMax, color_filter.rMax])
    # Apply the thresholds
    mask = cv2.inRange(original_image, lower, upper)
    result = cv2.bitwise_and(original_image, original_image, mask=mask)

    return result


# apply adjustments to an HSV channel
# https://stackoverflow.com/questions/49697363/shifting-hsv-pixel-values-in-python-using-numpy
def shift_channel(c, amount):
    if amount > 0:
        lim = 255 - amount
        c[c >= lim] = 255
        c[c < lim] += amount
    elif amount < 0:
        amount = -amount
        lim = amount
        c[c <= lim] = 0
        c[c > lim] -= amount
    return c


# custom data structure to hold the state of an HSV filter
class HsvFilter:
    def __init__(
        self,
        hMin=None,
        sMin=None,
        vMin=None,
        hMax=None,
        sMax=None,
        vMax=None,
        sAdd=None,
        sSub=None,
        vAdd=None,
        vSub=None,
        groupthresh=None,
        eps=None,
        w=None,
        h=None,
    ):
        self.hMin = hMin
        self.sMin = sMin
        self.vMin = vMin
        self.hMax = hMax
        self.sMax = sMax
        self.vMax = vMax
        self.sAdd = sAdd
        self.sSub = sSub
        self.vAdd = vAdd
        self.vSub = vSub
        self.groupthresh = groupthresh
        self.eps = eps
        self.w = w
        self.h = h


class ColorsFilter:
    def __init__(
        self,
        bMin=None,
        gMin=None,
        rMin=None,
        bMax=None,
        gMax=None,
        rMax=None,
        eps=None,
        groupthresh=None,
        minw=None,
        minh=None,
        maxw=None,
        maxh=None,
    ):
        self.bMin = bMin
        self.gMin = gMin
        self.rMin = rMin
        self.bMax = bMax
        self.gMax = gMax
        self.rMax = rMax
        self.eps = eps
        self.groupthresh = groupthresh
        self.minw = maxw
        self.minh = minh
        self.maxw = maxw
        self.maxh = maxh


if __name__ == "__main__":
    HANDLE = 0x00F90FA4
    USE_HSV = False
    USE_COLORS = True

    if USE_HSV:
        init_control_gui_hsv()
    if USE_COLORS:
        init_control_gui_color()

    while True:
        img_hsv = take_screenshot(HANDLE, dict(left=0, right=1024, top=165, bottom=700))
        img_color = img_hsv.copy()

        if USE_HSV:
            img_hsv_grouped = img_hsv.copy()
            processed_hsv = apply_hsv_filters(img_hsv)
            cv2.imshow("processed_hsv", processed_hsv)
            cv2.waitKey(1)
            hsv_filters = get_hsv_filter_from_controls()
            _hsv_lower = np.array([hsv_filters.hMin, hsv_filters.sMin, hsv_filters.vMin])
            _hsv_upper = np.array([hsv_filters.hMax, hsv_filters.sMax, hsv_filters.vMax])
            hsv = cv2.cvtColor(img_hsv, cv2.COLOR_BGR2HSV)
            hsv_binary = cv2.inRange(hsv, _hsv_lower, _hsv_upper)
            hsv_contours, _ = cv2.findContours(
                hsv_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            hsv_rects = [cv2.boundingRect(cnt) for cnt in hsv_contours]
            for x, y, w, h in hsv_rects:
                if w >= hsv_filters.w and h >= hsv_filters.h:
                    cv2.rectangle(img_hsv, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.imshow("contoured_hsv", img_hsv)
            cv2.waitKey(1)

            hsv_groups = cv2.groupRectangles(hsv_rects, hsv_filters.groupthresh, hsv_filters.eps)

            for rect in hsv_groups[0]:
                x, y, w, h = rect
                if w >= hsv_filters.w and h >= hsv_filters.h:
                    cv2.rectangle(img_hsv_grouped, (x, y), (x + w, y + h), (0, 0, 255), 3)
            cv2.imshow("contoured_hsv_grouped", img_hsv_grouped)
            cv2.waitKey(1)

        if USE_COLORS:
            processed_color = apply_color_filters(img_color)
            cv2.imshow("processed_color", processed_color)

            colors_filters = get_colors_filter_from_controls()
            _colors_lower = np.array(
                [colors_filters.bMin, colors_filters.gMin, colors_filters.rMin]
            )
            _colors_upper = np.array(
                [colors_filters.bMax, colors_filters.gMax, colors_filters.rMax]
            )
            colors_binary = cv2.inRange(img_color, _colors_lower, _colors_upper)
            cv2.imshow("colors_binary", colors_binary)
            colors_contours, _ = cv2.findContours(
                colors_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            img_color_cnt = img_color.copy()
            img_color_rect = img_color.copy()
            img_color_grouped = img_color.copy()
            img_color_hull = img_color.copy()
            for cnt in colors_contours:
                cv2.drawContours(img_color_cnt, [cnt], 0, (0, 255, 0), 3)
            colors_rects = [cv2.boundingRect(cnt) for cnt in colors_contours]
            for x, y, w, h in colors_rects:
                if colors_filters.minw <= w <= colors_filters.maxw and colors_filters.minh <= h <= colors_filters.maxh:
                    cv2.rectangle(img_color_rect, (x, y), (x + w, y + h), (0, 255, 0), 3)

            grouped = cv2.groupRectangles(colors_rects, 1, colors_filters.eps)
            for x, y, w, h in grouped[0]:
                if colors_filters.minw <= w <= colors_filters.maxw and colors_filters.minh <= h <= colors_filters.maxh:
                    cv2.rectangle(img_color_grouped, (x, y), (x + w, y + h), (0, 0, 255), 3)

            hulls = [cv2.convexHull(cnt) for cnt in colors_contours]
            for hull in hulls:
                cv2.drawContours(img_color_hull, [hull], 0, (0, 255, 0), 3)
            cv2.imshow("contoured_color_cnt", img_color_cnt)
            cv2.imshow("contoured_color_rect", img_color_rect)
            cv2.imshow("contoured_color_grouped", img_color_grouped)
            cv2.imshow("contoured_color_hull", img_color_hull)
            cv2.waitKey(1)
