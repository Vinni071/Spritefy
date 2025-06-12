import os
import glob
from flask import Flask, jsonify, send_from_directory, request, Response
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import json

# --------------------------------------------------------------------------
# This backend is designed based on the requirements from the PDF.
# It uses Object-Oriented principles, handles file manipulation, and
# is structured to be modular and extendable.
#
# To Run:
# 1. Install dependencies: pip install Flask mutagen
# 2. Create a folder named 'music' in the same directory as this script.
# 3. Place your .mp3 files inside the 'music' folder.
# 4. Run the script: python your_script_name.py
# 5. Open the HTML file in your browser.
# --------------------------------------------------------------------------


# --- 1. Object-Oriented Programming & Modularity ---
# We define classes for our core concepts: Song and MusicLibrary.
# This makes the code organized, reusable, and easier to maintain.

class Song:
    """Represents a single song file with its metadata."""
    def __init__(self, filepath, song_id):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.id = song_id
        self.title = self.filename
        self.artist = "Unknown Artist"
        self.album = "Unknown Album"
        self.duration = 0
        
        # --- 3. File Manipulation & Serialization ---
        # Here we read metadata directly from the audio files.
        try:
            if filepath.lower().endswith('.mp3'):
                audio = MP3(filepath, ID3=EasyID3)
                self.title = audio.get('title', [self.title])[0]
                self.artist = audio.get('artist', [self.artist])[0]
                self.album = audio.get('album', [self.album])[0]
                self.duration = audio.info.length
        except Exception as e:
            print(f"Could not read metadata for {self.filename}: {e}")

    def to_dict(self):
        """Serializes the Song object to a dictionary for JSON responses."""
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration
        }

# --- 5. Design Patterns: Singleton ---
# We use a Singleton pattern for the MusicLibrary to ensure there's only one
# instance managing the collection of songs throughout the application.

class MusicLibrary:
    """Manages the collection of all songs."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MusicLibrary, cls).__new__(cls)
        return cls._instance

    def __init__(self, music_folder='music'):
        # This check prevents re-initialization on subsequent calls
        if not hasattr(self, 'initialized'):
            self.music_folder = music_folder
            self.songs = []
            self.scan_songs()
            self.initialized = True
            
    def scan_songs(self):
        """Scans the music directory and populates the song list."""
        print(f"Scanning for music in '{self.music_folder}' directory...")
        self.songs = []
        # --- 2. Data Structures ---
        # We use a list to store songs and a dictionary (via glob) for lookup.
        # For a larger library, a hash table would be more explicit for faster lookups.
        for index, filepath in enumerate(glob.glob(os.path.join(self.music_folder, '*.mp3'))):
            self.songs.append(Song(filepath, index))
        print(f"Found {len(self.songs)} songs.")

    def get_all_songs(self):
        """Returns a list of all songs, serialized as dictionaries."""
        return [song.to_dict() for song in self.songs]

    def get_song_by_filename(self, filename):
        """Finds a song object by its filename."""
        for song in self.songs:
            if song.filename == filename:
                return song
        return None

# --- Flask Application Setup ---
app = Flask(__name__, static_folder=None) # We don't need a static folder for this setup
library = MusicLibrary(music_folder='music')

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves the main HTML file."""
    # This assumes your HTML file is named 'spritefy_player.html'
    return send_from_directory('.', 'spritefy_player.html')
    
@app.route('/api/songs', methods=['GET'])
def get_songs():
    """API endpoint to get the list of all available songs."""
    return jsonify(library.get_all_songs())

@app.route('/api/stream/<path:filename>')
def stream_audio(filename):
    """API endpoint to stream a specific audio file."""
    song = library.get_song_by_filename(filename)
    if not song:
        return "Song not found", 404
        
    return send_from_directory(library.music_folder, filename)

if __name__ == '__main__':
    # Check if the music directory exists
    if not os.path.exists('music'):
        os.makedirs('music')
        print("Created 'music' directory. Please add your .mp3 files there.")
    
    # Run the Flask app
    app.run(debug=True, port=5000)
