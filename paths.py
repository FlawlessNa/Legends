import os

ROOT = os.path.dirname(__file__)


def get_tesseract():
    if os.path.exists(
        os.path.join(os.environ["PROGRAMFILES"], "Tesseract-OCR/Tesseract.exe")
    ):
        return os.path.join(os.environ["PROGRAMFILES"], "Tesseract-OCR/Tesseract.exe")
    elif os.path.exists(
        os.path.join(
            os.environ["LOCALAPPDATA"], "Programs", "Tesseract-OCR/Tesseract.exe"
        )
    ):
        return os.path.join(
            os.environ["LOCALAPPDATA"], "Programs", "Tesseract-OCR/Tesseract.exe"
        )


TESSERACT = get_tesseract()
