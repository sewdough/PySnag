import sys
import os
import subprocess
import configparser
import shutil
from datetime import timedelta

# Read config.ini for ffmpeg configuration and update PATH if necessary
config = configparser.ConfigParser()
config.read('config.ini')
if 'FFmpeg' in config and config['FFmpeg'].get('path'):
    ffmpeg_dir = config['FFmpeg']['path']
    if ffmpeg_dir:
        os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QListWidget, QFileDialog, QProgressBar, QLabel, QMessageBox,
    QInputDialog, QMenu, QTabWidget, QSpacerItem, QSizePolicy, QDialog, QComboBox
)
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, Qt, QSize
from PyQt5.QtGui import QPalette, QColor

import yt_dlp

# ---------------------------
# Helper Function: Get Video Resolution
# ---------------------------
def get_video_resolution(filename):
    """Get the height (in pixels) of the first video stream using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", filename],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        res = result.stdout.strip()
        return int(res) if res.isdigit() else None
    except Exception:
        return None

# ---------------------------
# Helper Function: Conversion Parameter Selection
# ---------------------------
def choose_conversion_parameters(parent, input_file=None):
    """
    Presents a dialog to choose conversion parameters.
    If a valid input_file is provided for video conversion, the function detects
    the source resolution and appends " (UPSCALED)" to higher target resolution options.
    Also, it updates the resolution prompt to display the source resolution.
    """
    category, ok = QInputDialog.getItem(parent, "Select Conversion Category", "Category:", ["Audio", "Video"], 0, False)
    if not ok:
        return None
    if category == "Audio":
        audio_format, ok = QInputDialog.getItem(parent, "Select Audio Format", "Format:", ["MP3", "WAV", "AIFF", "FLAC"], 0, False)
        if not ok:
            return None
        if audio_format == "MP3":
            bitrate, ok = QInputDialog.getItem(parent, "Select Audio Quality", "Bitrate (kbps):", ["320", "256", "128"], 0, False)
            if not ok:
                return None
            conv_type = f"audio:{audio_format}:{bitrate}"
        else:
            conv_type = f"audio:{audio_format}"
    else:  # Video
        video_format, ok = QInputDialog.getItem(parent, "Select Video Format", "Format:", ["MP4", "AVI", "MKV", "WEBM", "MOV"], 0, False)
        if not ok:
            return None
        # Define available resolution options with numeric mapping
        resolutions = {"1080p": "1080", "2K": "1440", "4K": "2160"}
        source_res = get_video_resolution(input_file) if input_file and os.path.exists(input_file) else None
        resolution_options = []
        for disp, num in resolutions.items():
            if source_res is not None and int(num) > source_res:
                resolution_options.append(f"{disp} (UPSCALED)")
            else:
                resolution_options.append(disp)
        # Update the prompt to include the source resolution if available
        prompt_text = f"Resolution (source: {source_res}p)" if source_res else "Resolution:"
        resolution, ok = QInputDialog.getItem(parent, "Select Resolution", prompt_text, resolution_options, 0, False)
        if not ok:
            return None
        resolution = resolution.replace(" (UPSCALED)", "")
        numeric_resolution = resolutions[resolution]
        conv_type = f"video:{video_format}:{numeric_resolution}"
    return conv_type

# ---------------------------
# ConversionThread: ETA and status updates
# ---------------------------
class ConversionThread(QThread):
    progress_update = pyqtSignal(int, str)  # percent, remaining time
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, input_file, conversion_type, performance_mode=False):
        """
        conversion_type format: "media:format[:parameter]"
        For video: "video:MP4:1080" (or AVI, MKV, WEBM, MOV)
        For audio: "audio:MP3:320" or "audio:WAV" (or AIFF, FLAC)
        performance_mode: Boolean flag to enable optimized ffmpeg parameters.
        """
        super().__init__()
        self.input_file = input_file
        self.conversion_type = conversion_type
        self.performance_mode = performance_mode

    def get_duration(self, filename):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", filename],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return float(result.stdout.strip())
        except Exception:
            return None

    def run(self):
        if shutil.which("ffmpeg") is None:
            self.error.emit("ffmpeg executable not found in PATH.")
            return
        if not os.path.exists(self.input_file):
            self.error.emit("Input file not found: " + self.input_file)
            return

        total_duration = self.get_duration(self.input_file)
        if total_duration is None:
            self.error.emit("Could not determine input file duration.")
            return

        try:
            parts = self.conversion_type.split(":")
            if len(parts) < 2:
                self.error.emit("Unsupported conversion type format.")
                return

            media_type = parts[0].lower()  # "audio" or "video"
            fmt = parts[1].lower()         # output format
            output_file = os.path.splitext(self.input_file)[0]
            cmd = ['ffmpeg', '-y', '-i', self.input_file]
            
            if media_type == "audio":
                cmd.append("-vn")
                if fmt == "mp3":
                    if len(parts) < 3:
                        self.error.emit("Bitrate not specified for MP3 conversion.")
                        return
                    bitrate = parts[2]
                    output_file += f'_{bitrate}kbps.mp3'
                    cmd.extend(['-b:a', f'{bitrate}k'])
                elif fmt == "wav":
                    output_file += f'.{fmt}'
                elif fmt == "aiff":
                    output_file += f'.{fmt}'
                    cmd.extend(['-c:a', 'pcm_s16le'])
                elif fmt == "flac":
                    output_file += f'.{fmt}'
                    cmd.extend(['-c:a', 'flac'])
                else:
                    output_file += f'.{fmt}'
            elif media_type == "video":
                if len(parts) < 3:
                    self.error.emit("Resolution not specified for video conversion.")
                    return
                target_resolution = parts[2]
                source_resolution = get_video_resolution(self.input_file)
                # Determine output file naming based on resolution comparison
                if source_resolution:
                    if int(target_resolution) == source_resolution:
                        output_file += f' - {target_resolution}p (NO SCALING).{fmt}'
                    elif int(target_resolution) > source_resolution:
                        output_file += f' - {target_resolution}p (UPSCALED).{fmt}'
                    else:
                        output_file += f' - {target_resolution}p.{fmt}'
                else:
                    output_file += f' - {target_resolution}p.{fmt}'

                # Build ffmpeg command based on whether scaling is needed
                if source_resolution and int(target_resolution) == source_resolution:
                    # Use stream copy to preserve quality when no scaling is needed
                    cmd.extend(['-c:v', 'copy'])
                else:
                    # Apply scaling with a high-quality Lanczos filter
                    cmd.extend(['-vf', f'scale=-2:{target_resolution}:flags=lanczos'])
                    if self.performance_mode:
                        if fmt == "mp4":
                            cmd.extend(["-c:v", "h264_nvenc", "-preset", "fast"])
                        else:
                            cmd.extend(["-threads", "0"])
            else:
                self.error.emit("Unsupported media type.")
                return

            cmd.append(output_file)
            cmd.extend(['-progress', 'pipe:1'])
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            current_time = 0.0
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("out_time="):
                    out_time_str = line.split("=")[1]
                    try:
                        h, m, s = out_time_str.split(":")
                        seconds = float(h) * 3600 + float(m) * 60 + float(s)
                    except Exception:
                        seconds = 0.0
                    current_time = seconds
                    percent = int((current_time / total_duration) * 100)
                    remaining = total_duration - current_time
                    rem_td = timedelta(seconds=int(remaining))
                    remaining_str = str(rem_td)
                    self.progress_update.emit(percent, remaining_str)
                elif line.startswith("out_time_ms="):
                    ms_str = line.split("=")[1]
                    try:
                        seconds = float(ms_str) / 1000000.0
                    except Exception:
                        seconds = 0.0
                    current_time = seconds
                    percent = int((current_time / total_duration) * 100)
                    remaining = total_duration - current_time
                    rem_td = timedelta(seconds=int(remaining))
                    remaining_str = str(rem_td)
                    self.progress_update.emit(percent, remaining_str)
                if "progress=end" in line:
                    break
            process.wait()
            self.finished.emit(output_file)
        except Exception as e:
            self.error.emit(str(e))

# ---------------------------
# DownloadThread: Standard YT and Shorts support.
# ---------------------------
class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, url, download_path, quality):
        """
        quality: for standard videos: "4k", "2k", "1080p", "720p", "480p"
                 for Shorts: use "Shorts"
        """
        super().__init__()
        self.url = url
        self.download_path = download_path
        self.quality = quality
        self.filename = None

    def run(self):
        quality_map = {
            "4k": "bestvideo[height=2160]+bestaudio/best",
            "2k": "bestvideo[height=1440]+bestaudio/best",
            "1080p": "bestvideo[height=1080]+bestaudio/best",
            "720p": "bestvideo[height=720]+bestaudio/best",
            "480p": "bestvideo[height=480]+bestaudio/best"
        }
        ydl_opts = {
            'outtmpl': os.path.join(self.download_path, '%(title)s.%(ext)s'),
            'progress_hooks': [],
        }
        def progress_hook(d):
            if d.get('status') == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    percent = int(downloaded / total * 100)
                    self.progress.emit(percent)
            elif d.get('status') == 'finished':
                self.progress.emit(100)
        ydl_opts['progress_hooks'].append(progress_hook)

        if self.quality == "Shorts":
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif self.quality in quality_map:
            ydl_opts['format'] = quality_map[self.quality]
        else:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                self.filename = ydl.prepare_filename(info)
            base, ext = os.path.splitext(self.filename)
            if self.quality in quality_map:
                new_file = base + f" - {self.quality}" + ext
            elif self.quality == "Shorts":
                new_file = base + " - SHORTS" + ext
            else:
                new_file = base + " - HIGH RES" + ext
            os.rename(self.filename, new_file)
            self.filename = new_file
            self.finished.emit(self.filename)
        except Exception as e:
            if self.quality in quality_map or self.quality == "Shorts":
                try:
                    ydl_opts['format'] = 'bestvideo+bestaudio/best'
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(self.url, download=True)
                        self.filename = ydl.prepare_filename(info)
                    base, ext = os.path.splitext(self.filename)
                    new_file = base + " - HIGH RES" + ext
                    os.rename(self.filename, new_file)
                    self.filename = new_file
                    self.finished.emit(self.filename)
                except Exception as e2:
                    self.error.emit(str(e2))
            else:
                self.error.emit(str(e))

# ---------------------------
# BatchDownloadDialog: For batch downloading/conversion of YouTube/Shorts videos.
# ---------------------------
class BatchDownloadDialog(QDialog):
    def __init__(self, parent, download_directory, is_shorts=False):
        super().__init__(parent)
        self.download_directory = download_directory
        self.is_shorts = is_shorts
        self.setWindowTitle("Batch Download" + (" - Shorts" if is_shorts else " - YouTube"))
        self.urls = []
        self.current_index = 0
        self.current_thread = None

        layout = QVBoxLayout(self)

        instructions_label = QLabel("Enter URLs in the fields below or paste a list (separated by commas or spaces):")
        layout.addWidget(instructions_label)

        # URL entry fields layout
        self.url_fields_layout = QVBoxLayout()
        self.url_fields = []
        for _ in range(3):
            line_edit = QLineEdit()
            self.url_fields.append(line_edit)
            self.url_fields_layout.addWidget(line_edit)
        layout.addLayout(self.url_fields_layout)

        self.add_field_button = QPushButton("+")
        self.add_field_button.clicked.connect(self.add_url_field)
        layout.addWidget(self.add_field_button)

        self.bulk_text = QLineEdit()
        self.bulk_text.setPlaceholderText("Or paste multiple URLs separated by spaces or commas")
        layout.addWidget(self.bulk_text)

        # For YouTube (non-shorts) allow quality selection
        if not self.is_shorts:
            quality_label = QLabel("Select Quality:")
            layout.addWidget(quality_label)
            self.quality_combo = QComboBox()
            self.quality_combo.addItems(["4k", "2k", "1080p", "720p", "480p"])
            layout.addWidget(self.quality_combo)
        else:
            self.quality_combo = None

        self.start_button = QPushButton("Start Batch Download")
        self.start_button.clicked.connect(self.start_batch_download)
        layout.addWidget(self.start_button)

        self.progress_list = QListWidget()
        layout.addWidget(self.progress_list)

    def add_url_field(self):
        new_field = QLineEdit()
        self.url_fields.append(new_field)
        self.url_fields_layout.addWidget(new_field)

    def start_batch_download(self):
        urls = [field.text().strip() for field in self.url_fields if field.text().strip()]
        bulk = self.bulk_text.text().strip()
        if bulk:
            bulk_urls = [u.strip() for u in bulk.replace(",", " ").split() if u.strip()]
            urls.extend(bulk_urls)
        self.urls = list(dict.fromkeys(urls))
        if not self.urls:
            QMessageBox.warning(self, "Input Error", "Please enter at least one URL.")
            return
        if self.quality_combo:
            self.selected_quality = self.quality_combo.currentText()
        else:
            self.selected_quality = "Shorts"
        self.progress_list.addItem(f"Starting batch download of {len(self.urls)} URL(s)...")
        self.current_index = 0
        self.start_next_download()

    def start_next_download(self):
        if self.current_index < len(self.urls):
            url = self.urls[self.current_index]
            if not self.is_shorts and "youtube.com/shorts/" in url:
                url = url.replace("shorts/", "watch?v=")
            self.progress_list.addItem(f"Downloading: {url}")
            self.current_thread = DownloadThread(url, self.download_directory, self.selected_quality)
            self.current_thread.finished.connect(self.download_finished)
            self.current_thread.error.connect(self.download_error)
            self.current_thread.progress.connect(lambda p: None)
            self.current_thread.start()
        else:
            self.progress_list.addItem("Batch download complete.")

    def download_finished(self, file_path):
        self.progress_list.addItem(f"Downloaded: {file_path}")
        if self.parent() and hasattr(self.parent(), 'download_list'):
            parent = self.parent()
            parent.download_list.addItem(file_path)
            parent.recent_downloads.append(file_path)
            parent.settings.setValue("recent_downloads", parent.recent_downloads)
        self.current_index += 1
        self.start_next_download()

    def download_error(self, error_message):
        self.progress_list.addItem(f"Error: {error_message}")
        self.current_index += 1
        self.start_next_download()

# ---------------------------
# MainWindow
# ---------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("SewDough", "PySnag")
        self.download_directory = self.settings.value("download_directory", os.path.expanduser("~"))
        self.recent_downloads = self.settings.value("recent_downloads", [])
        if not isinstance(self.recent_downloads, list):
            self.recent_downloads = [self.recent_downloads] if self.recent_downloads else []
        self.converted_files = self.settings.value("converted_files", [])
        if not isinstance(self.converted_files, list):
            self.converted_files = [self.converted_files] if self.converted_files else []
        self.downloaded_file_yt = None
        self.downloaded_file_shorts = None
        self.dark_mode = False
        self.performance_mode = False  # Flag for performance mode
        # Hold conversion threads to prevent premature destruction
        self.yt_conversion_thread = None
        self.shorts_conversion_thread = None
        self.context_conversion_thread = None

        # Main layout: top bar and content area
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_vlayout = QVBoxLayout()
        main_widget.setLayout(main_vlayout)

        # Top bar: Title on left and dark mode & performance mode toggles on right
        top_bar = QHBoxLayout()
        self.title_label = QLabel('<h3>PySnag v0.3a <a href="https://github.com/sewdough">By SewDough</a></h3>')
        self.title_label.setOpenExternalLinks(True)
        top_bar.addWidget(self.title_label)
        top_bar.addStretch()
        self.dark_mode_button = QPushButton("Dark Mode")
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)
        top_bar.addWidget(self.dark_mode_button)
        self.performance_mode_button = QPushButton("Performance Mode: OFF")
        self.performance_mode_button.clicked.connect(self.toggle_performance_mode)
        top_bar.addWidget(self.performance_mode_button)
        main_vlayout.addLayout(top_bar)

        # Content area: left panel and tabs
        content_layout = QHBoxLayout()
        main_vlayout.addLayout(content_layout)

        # Left Panel: Recent Downloads & Converted Files, Set Directory and Import File
        left_panel = QVBoxLayout()
        # Recent Downloads section
        recent_header_layout = QHBoxLayout()
        recent_label = QLabel("Recent Downloads")
        recent_label.setStyleSheet("font-size: 12pt;")
        recent_header_layout.addWidget(recent_label)
        recent_header_layout.addStretch()
        self.clear_recent_button = QPushButton("Clear")
        self.clear_recent_button.setFixedSize(QSize(60, 25))
        self.clear_recent_button.clicked.connect(self.clear_recent_downloads)
        recent_header_layout.addWidget(self.clear_recent_button)
        left_panel.addLayout(recent_header_layout)
        
        self.download_list = QListWidget()
        self.download_list.setMinimumHeight(150)
        for item in self.recent_downloads:
            self.download_list.addItem(item)
        self.download_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.download_list.customContextMenuRequested.connect(self.show_context_menu)
        self.download_list.itemDoubleClicked.connect(self.open_file_item)
        left_panel.addWidget(self.download_list)
        
        # Converted Files section
        converted_header_layout = QHBoxLayout()
        converted_label = QLabel("Converted Files")
        converted_label.setStyleSheet("font-size: 12pt;")
        converted_header_layout.addWidget(converted_label)
        converted_header_layout.addStretch()
        self.clear_converted_button = QPushButton("Clear")
        self.clear_converted_button.setFixedSize(QSize(60, 25))
        self.clear_converted_button.clicked.connect(self.clear_converted_files)
        converted_header_layout.addWidget(self.clear_converted_button)
        left_panel.addLayout(converted_header_layout)
        
        self.converted_list = QListWidget()
        self.converted_list.setMinimumHeight(150)
        for item in self.converted_files:
            self.converted_list.addItem(item)
        self.converted_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.converted_list.customContextMenuRequested.connect(self.show_context_menu_converted)
        left_panel.addWidget(self.converted_list)
        
        # Import and Set Directory buttons
        btn_layout = QHBoxLayout()
        self.import_file_button = QPushButton("Import File")
        self.import_file_button.clicked.connect(self.import_file)
        btn_layout.addWidget(self.import_file_button)
        self.set_dir_button = QPushButton("Set Directory")
        self.set_dir_button.clicked.connect(self.set_directory)
        btn_layout.addWidget(self.set_dir_button)
        left_panel.addLayout(btn_layout)
        
        content_layout.addLayout(left_panel)

        # Tab Widget for YouTube and Shorts Downloader
        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget)

        # YouTube Downloader Tab
        self.yt_tab = QWidget()
        yt_layout = QVBoxLayout()
        self.yt_tab.setLayout(yt_layout)
        self.yt_url_input = QLineEdit()
        self.yt_url_input.setPlaceholderText("Enter YouTube video URL here")
        self.yt_download_button = QPushButton("Download")
        self.yt_download_button.clicked.connect(self.start_download_yt)
        self.yt_progress_bar = QProgressBar()
        self.yt_progress_bar.setValue(0)
        yt_layout.addWidget(self.yt_url_input)
        yt_layout.addWidget(self.yt_download_button)
        self.yt_batch_button = QPushButton("Batch Download")
        self.yt_batch_button.clicked.connect(self.start_batch_download_yt)
        yt_layout.addWidget(self.yt_batch_button)
        yt_layout.addWidget(self.yt_progress_bar)
        self.yt_conversion_progress_bar = QProgressBar()
        self.yt_conversion_progress_bar.setRange(0, 0)
        yt_layout.addWidget(self.yt_conversion_progress_bar)
        self.yt_convert_button = QPushButton("Convert")
        self.yt_convert_button.clicked.connect(self.start_conversion_yt)
        self.yt_convert_button.setVisible(False)
        yt_layout.addWidget(self.yt_convert_button)
        self.yt_conversion_status = QLabel("")
        yt_layout.addWidget(self.yt_conversion_status)
        self.tab_widget.addTab(self.yt_tab, "YouTube Downloader")

        # Shorts Downloader Tab
        self.shorts_tab = QWidget()
        shorts_layout = QVBoxLayout()
        self.shorts_tab.setLayout(shorts_layout)
        self.shorts_url_input = QLineEdit()
        self.shorts_url_input.setPlaceholderText("Enter Shorts URL here")
        self.shorts_download_button = QPushButton("Download")
        self.shorts_download_button.clicked.connect(self.start_download_shorts)
        self.shorts_progress_bar = QProgressBar()
        self.shorts_progress_bar.setValue(0)
        shorts_layout.addWidget(self.shorts_url_input)
        shorts_layout.addWidget(self.shorts_download_button)
        self.shorts_batch_button = QPushButton("Batch Download")
        self.shorts_batch_button.clicked.connect(self.start_batch_download_shorts)
        shorts_layout.addWidget(self.shorts_batch_button)
        shorts_layout.addWidget(self.shorts_progress_bar)
        self.shorts_conversion_progress_bar = QProgressBar()
        self.shorts_conversion_progress_bar.setRange(0, 0)
        shorts_layout.addWidget(self.shorts_conversion_progress_bar)
        self.shorts_convert_button = QPushButton("Convert")
        self.shorts_convert_button.clicked.connect(self.start_conversion_shorts)
        self.shorts_convert_button.setVisible(False)
        shorts_layout.addWidget(self.shorts_convert_button)
        self.shorts_conversion_status = QLabel("")
        shorts_layout.addWidget(self.shorts_conversion_status)
        self.tab_widget.addTab(self.shorts_tab, "Shorts Downloader")

        self.setWindowTitle("PySnag v0.3a by SewDough")
        self.resize(900, 500)

    # ------------- Toggle Stylesheets -------------
    def toggle_dark_mode(self):
        if not self.dark_mode:
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor("#343541"))
            dark_palette.setColor(QPalette.WindowText, QColor("#FFFFFF"))
            dark_palette.setColor(QPalette.Base, QColor("#202123"))
            dark_palette.setColor(QPalette.AlternateBase, QColor("#343541"))
            dark_palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
            dark_palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
            dark_palette.setColor(QPalette.Text, QColor("#FFFFFF"))
            dark_palette.setColor(QPalette.Button, QColor("#000000"))
            dark_palette.setColor(QPalette.ButtonText, QColor("#FFFFFF"))
            dark_palette.setColor(QPalette.BrightText, QColor("#FF0000"))
            dark_palette.setColor(QPalette.Link, QColor("#61AFEF"))
            dark_palette.setColor(QPalette.Highlight, QColor("#61AFEF"))
            dark_palette.setColor(QPalette.HighlightedText, QColor("#000000"))
            QApplication.instance().setPalette(dark_palette)
            
            self.setStyleSheet("""
                QPushButton {
                    background-color: #000000;
                    color: white;
                    border: none;
                    padding: 5px;
                    border-radius: 8px;
                }
                QTabWidget::pane {
                    background-color: #1e2124;
                    border: 1px solid #000000;
                    border-radius: 8px;
                }
                QTabBar::tab {
                    background-color: #000000;
                    color: white;
                    padding: 5px;
                    border-radius: 8px;
                    margin: 2px;
                }
                QLineEdit {
                    background-color: #202123;
                    color: white;
                    padding: 3px;
                    border-radius: 8px;
                }
                QComboBox {
                    background-color: #202123;
                    color: white;
                    border: 1px solid #000000;
                    padding: 3px;
                    border-radius: 8px;
                }
                QComboBox QAbstractItemView {
                    background-color: #202123;
                    color: white;
                    selection-background-color: #61AFEF;
                    border-radius: 8px;
                }
                QMessageBox {
                    background-color: #343541;
                    color: white;
                    border-radius: 8px;
                }
                QInputDialog {
                    background-color: #343541;
                    color: white;
                    border-radius: 8px;
                }
            """)
            self.dark_mode_button.setText("Light Mode")
            self.dark_mode = True
        else:
            QApplication.instance().setPalette(QApplication.instance().style().standardPalette())
            self.setStyleSheet("")
            self.dark_mode_button.setText("Dark Mode")
            self.dark_mode = False

    def toggle_performance_mode(self):
        self.performance_mode = not self.performance_mode
        if self.performance_mode:
            self.performance_mode_button.setText("Performance Mode: ON")
        else:
            self.performance_mode_button.setText("Performance Mode: OFF")

    # ------------- Clear List Functions -------------
    def clear_recent_downloads(self):
        self.download_list.clear()
        self.recent_downloads = []
        self.settings.setValue("recent_downloads", self.recent_downloads)

    def clear_converted_files(self):
        self.converted_list.clear()
        self.converted_files = []
        self.settings.setValue("converted_files", self.converted_files)

    # ------------- Context Menus and Buttons -------------
    def set_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory", self.download_directory)
        if directory:
            self.download_directory = directory
            self.settings.setValue("download_directory", directory)

    def import_file(self):
        # Filter for accepted video and audio types
        file_filter = "Video Files (*.mp4 *.avi *.mkv *.webm *.mov);;Audio Files (*.mp3 *.wav *.aiff *.flac)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Import File for Conversion", "", file_filter)
        if file_path and os.path.exists(file_path):
            self.recent_downloads.append(file_path)
            self.download_list.addItem(file_path)
            self.settings.setValue("recent_downloads", self.recent_downloads)

    def show_context_menu(self, position):
        item = self.download_list.itemAt(position)
        if item is None:
            return
        menu = QMenu()
        open_action = menu.addAction("Open File")
        file_path = item.text() if hasattr(item, 'text') else item
        if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.webm', '.mov')):
            res = get_video_resolution(file_path)
            if res is not None:
                if res < 1080:
                    convert_text = "Convert (Upscale)"
                else:
                    convert_text = "Convert (No Scaling)"
            else:
                convert_text = "Convert"
            convert_action = menu.addAction(convert_text)
        else:
            convert_action = menu.addAction("Convert")
        location_action = menu.addAction("Open File Location")
        action = menu.exec_(self.download_list.viewport().mapToGlobal(position))
        if action == open_action:
            self.open_file_item(item)
        elif action == convert_action:
            self.context_convert(item.text())
        elif action == location_action:
            self.open_file_location(item.text())

    def show_context_menu_converted(self, position):
        item = self.converted_list.itemAt(position)
        if item is None:
            return
        menu = QMenu()
        open_action = menu.addAction("Open File")
        location_action = menu.addAction("Open File Location")
        action = menu.exec_(self.converted_list.viewport().mapToGlobal(position))
        if action == open_action:
            self.open_file_item(item)
        elif action == location_action:
            self.open_file_location(item.text())

    def open_file_item(self, item):
        file_path = item.text() if hasattr(item, 'text') else item
        if os.path.exists(file_path):
            try:
                os.startfile(file_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file: {e}")
        else:
            QMessageBox.critical(self, "Error", "File does not exist.")

    def context_convert(self, file_path):
        if not os.path.exists(file_path):
            QMessageBox.critical(self, "Error", "File does not exist.")
            return
        conv_type = choose_conversion_parameters(self, file_path)
        if conv_type is None:
            return
        self.context_conversion_thread = ConversionThread(file_path, conv_type, performance_mode=self.performance_mode)
        self.context_conversion_thread.progress_update.connect(lambda pct, rem: None)
        self.context_conversion_thread.finished.connect(lambda output: self._conversion_finished("context", output))
        self.context_conversion_thread.error.connect(lambda err: self._conversion_error("context", err))
        self.context_conversion_thread.start()

    def open_file_location(self, file_path):
        if os.path.exists(file_path):
            try:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(file_path)])
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file location: {e}")
        else:
            QMessageBox.critical(self, "Error", "File does not exist.")

    # ------------- Utility: Add Converted File -------------
    def add_converted_file(self, file_path):
        self.converted_list.addItem(file_path)
        self.converted_files.append(file_path)
        self.settings.setValue("converted_files", self.converted_files)

    # ------------- YouTube Video Support -------------
    def start_download_yt(self):
        url = self.yt_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Input Error", "Please enter a valid URL.")
            return
        if "youtube.com/shorts/" in url:
            url = url.replace("shorts/", "watch?v=")
        quality, ok = QInputDialog.getItem(self, "Select Download Quality", "Quality:",
                                             ["4k", "2k", "1080p", "720p", "480p"], 0, False)
        if not ok:
            return
        self.yt_download_button.setEnabled(False)
        self.yt_progress_bar.setValue(0)
        self.yt_convert_button.setVisible(False)
        self.yt_download_thread = DownloadThread(url, self.download_directory, quality)
        self.yt_download_thread.progress.connect(self.yt_progress_bar.setValue)
        self.yt_download_thread.finished.connect(self.yt_download_finished)
        self.yt_download_thread.error.connect(self.yt_download_error)
        self.yt_download_thread.start()

    def yt_download_finished(self, file_path):
        self.downloaded_file_yt = file_path
        self.recent_downloads.append(file_path)
        self.download_list.addItem(file_path)
        self.settings.setValue("recent_downloads", self.recent_downloads)
        self.yt_download_button.setEnabled(True)
        self.yt_convert_button.setVisible(True)
        QMessageBox.information(self, "Download Complete", f"File downloaded:\n{file_path}")

    def yt_download_error(self, error_message):
        QMessageBox.critical(self, "Download Error", error_message)
        self.yt_download_button.setEnabled(True)

    def start_conversion_yt(self):
        file_path = self.downloaded_file_yt
        if not file_path:
            QMessageBox.warning(self, "Conversion Error", "No file available for conversion.")
            return
        conv_type = choose_conversion_parameters(self, file_path)
        if conv_type is None:
            return
        self.yt_convert_button.setEnabled(False)
        self.yt_conversion_progress_bar.setRange(0, 0)
        self.yt_conversion_status.setText("")
        self.yt_conversion_thread = ConversionThread(file_path, conv_type, performance_mode=self.performance_mode)
        self.yt_conversion_thread.progress_update.connect(self.update_yt_conversion_status)
        self.yt_conversion_thread.finished.connect(lambda output: self._conversion_finished("yt", output))
        self.yt_conversion_thread.error.connect(lambda err: self._conversion_error("yt", err))
        self.yt_conversion_thread.start()

    def update_yt_conversion_status(self, percent, remaining):
        if self.yt_conversion_progress_bar.maximum() == 0:
            self.yt_conversion_progress_bar.setRange(0, 100)
        self.yt_conversion_progress_bar.setValue(percent)
        self.yt_conversion_status.setText(f"{percent}% completed, Time remaining: {remaining}")

    def _conversion_finished(self, mode, output):
        QMessageBox.information(self, "Conversion Complete", f"File converted:\n{output}")
        self.add_converted_file(output)
        if mode == "yt":
            self.yt_convert_button.setEnabled(True)
            self.yt_conversion_status.setText("Conversion complete.")
            self.yt_conversion_thread = None
        elif mode == "shorts":
            self.shorts_convert_button.setEnabled(True)
            self.shorts_conversion_status.setText("Conversion complete.")
            self.shorts_conversion_thread = None
        elif mode == "context":
            self.context_conversion_thread = None

    def _conversion_error(self, mode, error_message):
        QMessageBox.critical(self, "Conversion Error", error_message)
        if mode == "yt":
            self.yt_convert_button.setEnabled(True)
            self.yt_conversion_status.setText("")
            self.yt_conversion_thread = None
        elif mode == "shorts":
            self.shorts_convert_button.setEnabled(True)
            self.shorts_conversion_status.setText("")
            self.shorts_conversion_thread = None
        elif mode == "context":
            self.context_conversion_thread = None

    # ------------- YT Shorts Support -------------
    def start_download_shorts(self):
        url = self.shorts_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Input Error", "Please enter a valid URL.")
            return
        self.shorts_download_button.setEnabled(False)
        self.shorts_progress_bar.setValue(0)
        self.shorts_convert_button.setVisible(False)
        self.shorts_download_thread = DownloadThread(url, self.download_directory, "Shorts")
        self.shorts_download_thread.progress.connect(self.shorts_progress_bar.setValue)
        self.shorts_download_thread.finished.connect(self.shorts_download_finished)
        self.shorts_download_thread.error.connect(self.shorts_download_error)
        self.shorts_download_thread.start()

    def shorts_download_finished(self, file_path):
        self.downloaded_file_shorts = file_path
        self.recent_downloads.append(file_path)
        self.download_list.addItem(file_path)
        self.settings.setValue("recent_downloads", self.recent_downloads)
        self.shorts_download_button.setEnabled(True)
        self.shorts_convert_button.setVisible(True)
        QMessageBox.information(self, "Download Complete", f"File downloaded:\n{file_path}")

    def shorts_download_error(self, error_message):
        QMessageBox.critical(self, "Download Error", error_message)
        self.shorts_download_button.setEnabled(True)

    def start_conversion_shorts(self):
        file_path = self.downloaded_file_shorts
        if not file_path:
            QMessageBox.warning(self, "Conversion Error", "No file available for conversion.")
            return
        conv_type = choose_conversion_parameters(self, file_path)
        if conv_type is None:
            return
        self.shorts_convert_button.setEnabled(False)
        self.shorts_conversion_progress_bar.setRange(0, 0)
        self.shorts_conversion_status.setText("")
        self.shorts_conversion_thread = ConversionThread(file_path, conv_type, performance_mode=self.performance_mode)
        self.shorts_conversion_thread.progress_update.connect(self.update_shorts_conversion_status)
        self.shorts_conversion_thread.finished.connect(lambda output: self._conversion_finished("shorts", output))
        self.shorts_conversion_thread.error.connect(lambda err: self._conversion_error("shorts", err))
        self.shorts_conversion_thread.start()

    def update_shorts_conversion_status(self, percent, remaining):
        if self.shorts_conversion_progress_bar.maximum() == 0:
            self.shorts_conversion_progress_bar.setRange(0, 100)
        self.shorts_conversion_progress_bar.setValue(percent)
        self.shorts_conversion_status.setText(f"{percent}% completed, Time remaining: {remaining}")

    # ------------- Batch Download Handlers -------------
    def start_batch_download_yt(self):
        dialog = BatchDownloadDialog(self, self.download_directory, is_shorts=False)
        dialog.exec_()

    def start_batch_download_shorts(self):
        dialog = BatchDownloadDialog(self, self.download_directory, is_shorts=True)
        dialog.exec_()

# ---------------------------
# Main Entry Point
# ---------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
