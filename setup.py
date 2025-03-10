import os
import sys
import subprocess
import configparser
import urllib.request
import zipfile

def install_dependencies():
    print("Installing dependencies via pip...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'PyQt5', 'pytube', 'yt-dlp'])

def ffmpeg_in_path():
    try:
        subprocess.check_output(['ffmpeg', '-version'], stderr=subprocess.STDOUT)
        print("ffmpeg is already in your PATH.")
        return True
    except Exception:
        print("ffmpeg not found in PATH.")
        return False

def progress_hook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        percent = downloaded / total_size * 100
        sys.stdout.write(f"\rDownloading ffmpeg: {percent:5.1f}%")
        sys.stdout.flush()

def download_and_extract_ffmpeg():
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    dest_zip = "ffmpeg.zip"
    print(f"Downloading ffmpeg from {url} (this may take a while)...")
    try:
        urllib.request.urlretrieve(url, dest_zip, reporthook=progress_hook)
        sys.stdout.write("\n")
    except Exception as e:
        print("Error downloading ffmpeg:", e)
        return None

    extract_dir = os.path.join(os.getcwd(), "ffmpeg")
    if not os.path.exists(extract_dir):
        os.makedirs(extract_dir)
    print("Download complete. Extracting ffmpeg...")
    try:
        with zipfile.ZipFile(dest_zip, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        print("Error extracting ffmpeg:", e)
        return None
    finally:
        os.remove(dest_zip)

    # Look for the extracted folder
    subdirs = [d for d in os.listdir(extract_dir) if os.path.isdir(os.path.join(extract_dir, d))]
    if subdirs:
        ffmpeg_folder = os.path.join(extract_dir, subdirs[0])
        bin_dir = os.path.join(ffmpeg_folder, "bin")
        if os.path.isdir(bin_dir):
            print("ffmpeg extracted successfully to:", bin_dir)
            return bin_dir
    print("Could not locate ffmpeg bin folder in the extracted files.")
    return None

def write_config(ffmpeg_dir):
    config = configparser.ConfigParser()
    config['FFmpeg'] = {}
    config['FFmpeg']['path'] = ffmpeg_dir if ffmpeg_dir else ''
    with open('config.ini', 'w') as configfile:
        config.write(configfile)
    print("Configuration saved to config.ini.")

if __name__ == '__main__':
    try:
        install_dependencies()
    except subprocess.CalledProcessError as e:
        print("Error installing dependencies:", e)
        sys.exit(1)

    ffmpeg_dir = None
    if not ffmpeg_in_path():
        if sys.platform.startswith('win'):
            print("Attempting to download ffmpeg for Windows...")
            ffmpeg_dir = download_and_extract_ffmpeg()
            if ffmpeg_dir:
                # Prepend the ffmpeg bin directory to the PATH
                os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
                # Verify that ffmpeg is now available
                if ffmpeg_in_path():
                    print("ffmpeg is now available in PATH.")
                else:
                    print("ffmpeg still not found. You may need to add it manually later.")
            else:
                print("Automatic download of ffmpeg failed. Please install ffmpeg and add it to your PATH.")
        else:
            print("Automatic ffmpeg download is only supported on Windows. Please install ffmpeg and add it to your PATH manually.")
    else:
        # If ffmpeg is in PATH, get its directory using the 'where' command (Windows) or 'which' (Unix)
        try:
            if sys.platform.startswith('win'):
                ffmpeg_dir = subprocess.check_output(['where', 'ffmpeg']).decode().splitlines()[0]
                ffmpeg_dir = os.path.dirname(ffmpeg_dir)
            else:
                ffmpeg_dir = subprocess.check_output(['which', 'ffmpeg']).decode().strip()
                ffmpeg_dir = os.path.dirname(ffmpeg_dir)
        except Exception:
            ffmpeg_dir = ''

    write_config(ffmpeg_dir if ffmpeg_dir else '')
    print("Setup complete. You can now run the main application (e.g., pysnag.py).")
