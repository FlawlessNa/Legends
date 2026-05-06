"""Screen capture utilities for collecting training data."""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import cv2

# Import the existing screenshot function from botting utilities
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from botting.utilities.screenshots import take_screenshot


class ScreenCapture:
    """Screen capture utility for collecting training data."""
    
    def __init__(
        self,
        output_dir: Optional[str] = None,
        window_handle: Optional[int] = None
    ):
        """
        Initialize screen capture.
        
        Args:
            output_dir: Directory to save captured images
            window_handle: Window handle to capture (None for full screen)
        """
        from ..config import config
        
        self.output_dir = Path(output_dir or config.get('screen_capture.output_dir', 'ml_training/data/raw_images'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.window_handle = window_handle
    
    def capture_burst(
        self,
        count: int,
        prefix: str = "capture",
        interval: Optional[float] = None
    ) -> List[str]:
        """
        Capture multiple screenshots with intervals.
        
        Args:
            count: Number of screenshots to capture
            prefix: Filename prefix
            interval: Interval between captures in seconds
            
        Returns:
            List of paths to saved images
        """
        from ..config import config
        
        interval = interval if interval is not None else config.get('screen_capture.burst_interval', 0.5)
        
        filepaths = []
        
        print(f"\nCapturing {count} screenshots with {interval}s interval...")
        
        # Capture burst
        for i in range(count):
            # Use the existing take_screenshot function
            img_array = take_screenshot(handle=self.window_handle)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{prefix}_{timestamp}.jpg"
            filepath = self.output_dir / filename
            
            # Save image
            cv2.imwrite(str(filepath), img_array)
            
            filepaths.append(str(filepath))
            print(f"Captured {i+1}/{count}: {filepath.name}")
            
            if i < count - 1:  # Don't wait after last capture
                time.sleep(interval)
        
        print(f"\nCompleted! Captured {count} images to {self.output_dir}")
        return filepaths


def capture_burst(
    count: int,
    output_dir: Optional[str] = None,
    prefix: str = "capture",
    interval: float = 0.5,
    window_handle: Optional[int] = None
) -> List[str]:
    """
    Convenience function to capture multiple screenshots.
    
    Args:
        count: Number of screenshots
        output_dir: Directory to save images
        prefix: Filename prefix
        interval: Interval between captures
        window_handle: Window handle to capture
        
    Returns:
        List of paths to saved images
    """
    capturer = ScreenCapture(output_dir=output_dir, window_handle=window_handle)
    return capturer.capture_burst(
        count=count,
        prefix=prefix,
        interval=interval
    )
