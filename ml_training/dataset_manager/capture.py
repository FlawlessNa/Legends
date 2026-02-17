"""Screen capture utilities for collecting training data."""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import ImageGrab

from ..config import config


class ScreenCapture:
    """Screen capture utility for collecting training data."""
    
    def __init__(
        self,
        output_dir: Optional[str] = None,
        window_title: Optional[str] = None,
        region: Optional[Tuple[int, int, int, int]] = None
    ):
        """
        Initialize screen capture.
        
        Args:
            output_dir: Directory to save captured images
            window_title: Window title to focus (not used in current implementation)
            region: Capture region as (x, y, width, height), None for full screen
        """
        self.output_dir = Path(output_dir or config.get('screen_capture.output_dir', 'ml_training/data/raw_images'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.window_title = window_title or config.get('screen_capture.window_title', '')
        self.region = region or config.get('screen_capture.region')
        self.countdown = config.get('screen_capture.countdown', 3)
        self.burst_interval = config.get('screen_capture.burst_interval', 0.5)
    
    def capture_single(
        self,
        prefix: str = "capture",
        countdown: Optional[int] = None,
        show_countdown: bool = True
    ) -> str:
        """
        Capture a single screenshot.
        
        Args:
            prefix: Filename prefix
            countdown: Countdown before capture (uses config default if None)
            show_countdown: Whether to print countdown
            
        Returns:
            Path to saved image
        """
        countdown = countdown if countdown is not None else self.countdown
        
        # Countdown
        if countdown > 0:
            for i in range(countdown, 0, -1):
                if show_countdown:
                    print(f"Capturing in {i}...", end='\r')
                time.sleep(1)
            if show_countdown:
                print("Capturing now!      ")
        
        # Capture screenshot
        screenshot = ImageGrab.grab(bbox=self.region)
        
        # Convert to numpy array (RGB)
        img_array = np.array(screenshot)
        
        # Convert RGB to BGR for OpenCV
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{timestamp}.jpg"
        filepath = self.output_dir / filename
        
        # Save image
        cv2.imwrite(str(filepath), img_bgr)
        
        if show_countdown:
            print(f"Saved: {filepath}")
        
        return str(filepath)
    
    def capture_burst(
        self,
        count: int,
        prefix: str = "capture",
        countdown: Optional[int] = None,
        interval: Optional[float] = None
    ) -> List[str]:
        """
        Capture multiple screenshots with intervals.
        
        Args:
            count: Number of screenshots to capture
            prefix: Filename prefix
            countdown: Initial countdown before first capture
            interval: Interval between captures in seconds
            
        Returns:
            List of paths to saved images
        """
        countdown = countdown if countdown is not None else self.countdown
        interval = interval if interval is not None else self.burst_interval
        
        filepaths = []
        
        print(f"\nCapturing {count} screenshots with {interval}s interval...")
        
        # Initial countdown
        if countdown > 0:
            for i in range(countdown, 0, -1):
                print(f"Starting in {i}...", end='\r')
                time.sleep(1)
            print("Starting now!        ")
        
        # Capture burst
        for i in range(count):
            filepath = self.capture_single(
                prefix=prefix,
                countdown=0,
                show_countdown=False
            )
            filepaths.append(filepath)
            print(f"Captured {i+1}/{count}: {Path(filepath).name}")
            
            if i < count - 1:  # Don't wait after last capture
                time.sleep(interval)
        
        print(f"\nCompleted! Captured {count} images to {self.output_dir}")
        return filepaths
    
    def set_region(self, x: int, y: int, width: int, height: int) -> None:
        """
        Set capture region.
        
        Args:
            x: Left coordinate
            y: Top coordinate
            width: Region width
            height: Region height
        """
        self.region = (x, y, x + width, y + height)
    
    def reset_region(self) -> None:
        """Reset to full screen capture."""
        self.region = None


def capture_single(
    output_dir: Optional[str] = None,
    prefix: str = "capture",
    countdown: int = 3
) -> str:
    """
    Convenience function to capture a single screenshot.
    
    Args:
        output_dir: Directory to save image
        prefix: Filename prefix
        countdown: Countdown before capture
        
    Returns:
        Path to saved image
    """
    capturer = ScreenCapture(output_dir=output_dir)
    return capturer.capture_single(prefix=prefix, countdown=countdown)


def capture_burst(
    count: int,
    output_dir: Optional[str] = None,
    prefix: str = "capture",
    countdown: int = 3,
    interval: float = 0.5
) -> List[str]:
    """
    Convenience function to capture multiple screenshots.
    
    Args:
        count: Number of screenshots
        output_dir: Directory to save images
        prefix: Filename prefix
        countdown: Initial countdown
        interval: Interval between captures
        
    Returns:
        List of paths to saved images
    """
    capturer = ScreenCapture(output_dir=output_dir)
    return capturer.capture_burst(
        count=count,
        prefix=prefix,
        countdown=countdown,
        interval=interval
    )
