# PySnag
**A Python based YT Downloader / Converter (and general media converter)**

This supports video formats like **MP4**, **AVI**, **MKV**, **WEBM**, and **MOV**, and audio formats such as **MP3**, **WAV**, **AIFF**, and **FLAC**. It offers conversion options for various resolutions (**1080p**, **2K**, **4K**) and intelligently chooses between stream copying or re-encoding with high-quality scaling (using the **Lanczos filter**) to preserve quality, even upscaling when needed.

This project is designed to be user-friendly while providing robust conversion capabilities and batch processing support.

It comes packaged with a `setup.py` script that automatically installs **ffmpeg**, sets the path for ffmpeg conversion, and handles the pip dependencies, which is strongly recommended to use. Otherwise, it requires minimal manual setup on your end.

---

## Required Dependencies

- **Python:** 3.x  
- **Pip Installs:**  
  - `PyQt5`  
  - `yt-dlp`  
- **FFmpeg:** Must be installed and accessible via the system PATH  
- **Additional Modules:** `configparser`, `subprocess`, `shutil`, etc. (standard Python libraries)

> **Note:** It is strongly recommended to use the provided `setup.py` script for installation rather than performing manual installations.

---

## Installation

To install the script's dependencies, run:
```bash
python setup.py
```

Once this has finished, you can run the main script:

```bash
python pysnagv03.py
```

# Technical Breakdown
PySnag is built on top of PyQt5, which powers the graphical user interface, making the application both responsive and intuitive. 
The application uses multiple threads (via QThread) for tasks like video downloading and conversion, ensuring that the user interface remains responsive during long-running operations. 

**Notable functions include:**

+ get_video_resolution: Uses ffprobe to determine the resolution of the input video, a critical step to decide whether to apply stream copy or re-encode the video.
+ Conversion Logic: The script constructs dynamic ffmpeg commands to handle various conversion scenarios, including stream copying for identical resolutions and applying the Lanczos scaling filter for upscaling.
+ Download Integration: It leverages yt-dlp to download videos, supporting both single and batch downloads.
+ User Settings: The application utilizes QSettings to store recent downloads and converted files, ensuring a smooth user experience across sessions.
+ Contextual Menus: Dynamic context menus provide immediate feedback on whether a file will be upscaled or converted without scaling, enhancing user interaction.


# Changelog  v0.3a
- Added support for both YouTube and Shorts downloading.
- Integrated video conversion with intelligent scaling and stream copy.
- Context menu updates to indicate whether upscaling is needed.
- Batch downloading and conversion support.
- Improved settings management with QSettings.
