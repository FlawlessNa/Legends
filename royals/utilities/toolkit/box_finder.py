import cv2
import win32gui


def box_finder(handle: int, box: Box | None = None) -> Box:
    """
    Function that continuously takes screenshots and waits for user-input. Based on that given input, the box is slightly modified and a new screenshot is taken.
    Available commands:
        - Q: Exits and returns final box

        - A: Decreases width by 1 (increases left coordinate).
        - a: Increases width by 1 (decreases left coordinate).

        - D: Decreases width by 1 (decreases right coordinate).
        - d: Increases width by 1 (increases right coordinate).

        - W: Decreases height by 1 (increases top coordinate).
        - w: Increases height by 1 (decreases top coordinate).

        - S: Decreases height coordinate by 1 (decreases bottom coordinate).
        - s: Increases height coordinate by 1 (increases bottom coordinate).

    :return: final Box
    """
    if box is None:
        from royals.utilities.screenshots import (
            CLIENT_HORIZONTAL_MARGIN_PX,
            CLIENT_VERTICAL_MARGIN_PX,
        )

        left, top, right, bottom = win32gui.GetClientRect(handle)
        box = Box(
            left=left + CLIENT_HORIZONTAL_MARGIN_PX,
            top=top + CLIENT_VERTICAL_MARGIN_PX,
            right=right + CLIENT_HORIZONTAL_MARGIN_PX,
            bottom=bottom + CLIENT_VERTICAL_MARGIN_PX,
        )
    while True:
        screenshot = take_screenshot(handle, box)
        cv2.imshow("test", screenshot)
        key = cv2.waitKey(0)

        if key == ord("Q"):
            break

        elif key == ord("A"):
            box += Box(left=1, right=0, top=0, bottom=0, offset=True)
        elif key == ord("a"):
            box += Box(left=-1, right=0, top=0, bottom=0, offset=True)

        elif key == ord("D"):
            box += Box(left=0, right=-1, top=0, bottom=0, offset=True)
        elif key == ord("d"):
            box += Box(left=0, right=1, top=0, bottom=0, offset=True)

        elif key == ord("W"):
            box += Box(left=0, right=0, top=1, bottom=0, offset=True)
        elif key == ord("w"):
            box += Box(left=0, right=0, top=-1, bottom=0, offset=True)

        elif key == ord("S"):
            box += Box(left=0, right=0, top=0, bottom=-1, offset=True)
        elif key == ord("s"):
            box += Box(left=0, right=0, top=0, bottom=1, offset=True)

        else:
            continue

    print(f"Final Box: {box}")
    return box
