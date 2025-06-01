import os
import requests
import time
import logging
from PIL import Image, ImageStat
import io
from typing import Optional, Tuple

logger = logging.getLogger("ImageValidator")


class ImageValidator:
    """Enhanced image download and validation system for Books-A-Million products"""

    def __init__(self, image_dir: str, min_file_size: int = 500):
        self.image_dir = image_dir
        self.min_file_size = min_file_size
        os.makedirs(image_dir, exist_ok=True)

        # Common headers to appear as a real browser
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def construct_image_url(self, pid: str) -> str:
        """
        Construct the Books-A-Million image URL from PID

        Args:
            pid: Product ID (e.g., F0820650853500)

        Returns:
            Constructed image URL
        """
        # Remove the 'F' prefix if present
        clean_pid = pid[1:] if pid.startswith('F') else pid

        # Construct URL: https://covers.booksamillion.com/covers/gift/0/82/065/085/0820650853500-1.jpg
        url = f"https://covers.booksamillion.com/covers/gift/{clean_pid[0]}/{clean_pid[1:3]}/{clean_pid[3:6]}/{clean_pid[6:9]}/{clean_pid}-1.jpg"

        return url

    def check_url_exists(self, url: str) -> bool:
        """
        Quick HEAD request to check if URL exists before downloading

        Args:
            url: Image URL to check

        Returns:
            True if URL appears to exist, False otherwise
        """
        try:
            response = requests.head(url, headers=self.headers, timeout=10, allow_redirects=True)

            # Check status code
            if response.status_code != 200:
                logger.debug(f"HEAD request failed: {response.status_code}")
                return False

            # Check Content-Length if available
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) < self.min_file_size:
                logger.debug(f"Content-Length too small: {content_length} bytes")
                return False

            # Check Content-Type
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.debug(f"Invalid Content-Type: {content_type}")
                return False

            return True

        except Exception as e:
            logger.debug(f"HEAD request error: {str(e)}")
            return False

    def is_placeholder_image(self, image_data: bytes) -> bool:
        """
        Check if image is a placeholder (white, transparent, or single color)

        Args:
            image_data: Raw image bytes

        Returns:
            True if image appears to be a placeholder
        """
        try:
            # Open image with PIL
            img = Image.open(io.BytesIO(image_data))

            # Convert to RGB to handle transparency
            if img.mode in ('RGBA', 'LA', 'P'):
                # Check for transparency
                if img.mode == 'RGBA':
                    # Check if image is mostly transparent
                    alpha_channel = img.split()[-1]  # Get alpha channel
                    alpha_stat = ImageStat.Stat(alpha_channel)
                    if alpha_stat.mean[0] < 50:  # Very transparent
                        logger.debug("Image is mostly transparent")
                        return True

                # Convert to RGB for color analysis
                img = img.convert('RGB')

            # Check image dimensions (too small = likely placeholder)
            width, height = img.size
            if width < 100 or height < 100:
                logger.debug(f"Image too small: {width}x{height}")
                return True

            # Analyze colors to detect solid/near-solid color images
            stat = ImageStat.Stat(img)

            # Check if image is mostly white
            # RGB values close to (255, 255, 255)
            if all(mean > 240 for mean in stat.mean):
                logger.debug("Image is mostly white")
                return True

            # Check for very low color variance (solid color)
            if all(stddev < 10 for stddev in stat.stddev):
                logger.debug("Image has very low color variance (solid color)")
                return True

            # Sample pixels to check for patterns
            # Take samples from corners and center
            sample_points = [
                (10, 10), (width - 10, 10), (10, height - 10), (width - 10, height - 10),
                (width // 2, height // 2)
            ]

            colors = []
            for x, y in sample_points:
                try:
                    color = img.getpixel((x, y))
                    colors.append(color)
                except IndexError:
                    continue

            # If all sampled colors are very similar, it's likely a placeholder
            if len(colors) >= 3:
                # Check if all colors are very similar (within threshold)
                first_color = colors[0]
                similar_count = sum(1 for color in colors
                                    if all(abs(a - b) < 20 for a, b in zip(color, first_color)))

                if similar_count == len(colors):
                    logger.debug("All sampled pixels are very similar")
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error analyzing image: {str(e)}")
            return True  # Assume it's bad if we can't analyze it

    def download_and_validate_image(self, pid: str, url: Optional[str] = None) -> Optional[str]:
        """
        Download and validate image, save if valid

        Args:
            pid: Product ID
            url: Optional image URL (will construct if not provided)

        Returns:
            Local file path if successful, None otherwise
        """
        if not url:
            url = self.construct_image_url(pid)

        local_path = os.path.join(self.image_dir, f"{pid}.jpg")

        # Check if we already have this image
        if os.path.exists(local_path):
            logger.debug(f"Image already exists for {pid}")
            return local_path

        logger.info(f"Downloading image for {pid} from {url}")

        # Step 1: Quick HEAD check
        if not self.check_url_exists(url):
            logger.debug(f"HEAD check failed for {pid}")
            return None

        try:
            # Step 2: Download the image
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code != 200:
                logger.warning(f"Download failed for {pid}: HTTP {response.status_code}")
                return None

            image_data = response.content

            # Step 3: Basic size check
            if len(image_data) < self.min_file_size:
                logger.debug(f"Image too small for {pid}: {len(image_data)} bytes")
                return None

            # Step 4: Validate image format
            try:
                img = Image.open(io.BytesIO(image_data))
                img.verify()  # Verify it's a valid image
            except Exception as e:
                logger.debug(f"Invalid image format for {pid}: {str(e)}")
                return None

            # Step 5: Check if it's a placeholder
            if self.is_placeholder_image(image_data):
                logger.debug(f"Image appears to be placeholder for {pid}")
                return None

            # Step 6: Save the validated image
            with open(local_path, 'wb') as f:
                f.write(image_data)

            logger.info(f"Successfully saved validated image for {pid}: {local_path}")
            return local_path

        except Exception as e:
            logger.error(f"Error downloading image for {pid}: {str(e)}")
            return None

    def batch_download_images(self, pids: list, delay: float = 0.5) -> dict:
        """
        Download multiple images with delay between requests

        Args:
            pids: List of product IDs
            delay: Delay between requests in seconds

        Returns:
            Dictionary mapping PID to local file path (or None if failed)
        """
        results = {}

        for i, pid in enumerate(pids):
            if i > 0:  # Add delay between requests
                time.sleep(delay)

            result = self.download_and_validate_image(pid)
            results[pid] = result

            logger.info(f"Progress: {i + 1}/{len(pids)} - {pid}: {'✓' if result else '✗'}")

        successful = sum(1 for path in results.values() if path is not None)
        logger.info(f"Batch complete: {successful}/{len(pids)} images downloaded successfully")

        return results


# Integration example for your Books-A-Million class
def integrate_with_booksamillion_class():
    """
    Example of how to integrate this with your existing Booksamillion class
    """

    # Add this to your Booksamillion.__init__ method:
    """
    self.image_validator = ImageValidator(
        image_dir=os.path.join(self.project_root, "images"),
        min_file_size=500  # Adjust as needed
    )
    """

    # Replace your save_image_locally method with this:
    """
    def save_image_locally(self, pid, image_url):
        '''Download and validate product image locally'''
        try:
            # Try the provided URL first
            local_path = self.image_validator.download_and_validate_image(pid, image_url)

            # If that fails, try constructing the URL from PID
            if not local_path:
                logger.debug(f"Original URL failed for {pid}, trying constructed URL")
                local_path = self.image_validator.download_and_validate_image(pid)

            return local_path or self._get_placeholder_image_path()

        except Exception as e:
            logger.error(f"Error in save_image_locally for {pid}: {str(e)}")
            return self._get_placeholder_image_path()
    """


# Example usage
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Create validator
    validator = ImageValidator(image_dir="./images", min_file_size=500)

    # Test with some PIDs
    test_pids = [
        "F0820650853500",
        "F820650412493",
        "F820650413315"
    ]

    # Download images
    results = validator.batch_download_images(test_pids)

    # Print results
    for pid, path in results.items():
        if path:
            print(f"✓ {pid}: {path}")
        else:
            print(f"✗ {pid}: Failed validation")