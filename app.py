import os
import glob
from flask import Flask, jsonify, send_from_directory, request, Response
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import json

# --------------------------------------------------------------------------
# Este backend foi projetado com base nos requisitos do PDF.
# Ele usa princípios de Orientação a Objetos, lida com manipulação de arquivos e
# é estruturado para ser modular e extensível.
#
# Para Executar:
# 1. Instale as dependências: pip install Flask mutagen
# 2. Crie uma pasta chamada 'music' no mesmo diretório deste script.
# 3. Coloque seus arquivos .mp3 dentro da pasta 'music'.
# 4. Execute o script: python app.py
# 5. Abra o arquivo HTML no seu navegador.
# --------------------------------------------------------------------------


# --- 1. Programação Orientada a Objetos e Modularidade ---
# Definimos classes para nossos conceitos principais: Song e MusicLibrary.
# Isso torna o código organizado, reutilizável e mais fácil de manter.

class Song:
    """Representa um único arquivo de música com seus metadados."""
    def __init__(self, filepath, song_id):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.id = song_id
        self.title = self.filename
        self.artist = "Artista Desconhecido"
        self.album = "Álbum Desconhecido"
        self.duration = 0
        
        # --- 3. Manipulação de Arquivos e Serialização ---
        # Aqui lemos os metadados diretamente dos arquivos de áudio.
        try:
            if filepath.lower().endswith('.mp3'):
                audio = MP3(filepath, ID3=EasyID3)
                self.title = audio.get('title', [self.title])[0]
                self.artist = audio.get('artist', [self.artist])[0]
                self.album = audio.get('album', [self.album])[0]
                self.duration = audio.info.length
        except Exception as e:
            print(f"Não foi possível ler os metadados de {self.filename}: {e}")

    def to_dict(self):
        """Serializa o objeto Song para um dicionário para respostas JSON."""
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration
        }

# --- 5. Padrões de Projeto: Singleton ---
# Usamos um padrão Singleton para a MusicLibrary para garantir que haja apenas uma
# instância a gerir a coleção de músicas em toda a aplicação.

class MusicLibrary:
    """Gerencia a coleção de todas as músicas e playlists."""
    _instance = None
    PLAYLISTS_FILE = 'playlists.json' # NEW: File to store playlists

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MusicLibrary, cls).__new__(cls)
        return cls._instance

    def __init__(self, music_folder='music'):
        # Esta verificação impede a reinicialização em chamadas subsequentes
        if not hasattr(self, 'initialized'):
            self.music_folder = music_folder
            self.songs = []
            self.playlists = {} 
            self._load_playlists() # NEW: Load playlists on startup
            self.scan_songs()
            self.initialized = True
            
    def _load_playlists(self):
        """NEW: Loads playlists from the JSON file if it exists."""
        try:
            if os.path.exists(self.PLAYLISTS_FILE):
                with open(self.PLAYLISTS_FILE, 'r') as f:
                    self.playlists = json.load(f)
                    print(f"Playlists carregadas de {self.PLAYLISTS_FILE}")
        except Exception as e:
            print(f"Erro ao carregar o arquivo de playlists: {e}")
            self.playlists = {}

    def _save_playlists(self):
        """NEW: Saves the current playlists to the JSON file."""
        try:
            with open(self.PLAYLISTS_FILE, 'w') as f:
                json.dump(self.playlists, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar o arquivo de playlists: {e}")

    def scan_songs(self):
        """Verifica o diretório de músicas e preenche la lista de músicas."""
        print(f"A procurar músicas no diretório '{self.music_folder}'...")
        self.songs = []
        # --- 2. Estruturas de Dados ---
        # Usamos uma lista para armazenar as músicas e um dicionário (via glob) para pesquisa.
        for index, filepath in enumerate(glob.glob(os.path.join(self.music_folder, '*.mp3'))):
            self.songs.append(Song(filepath, index))
        print(f"Encontradas {len(self.songs)} músicas.")

    def get_all_songs(self):
        """Retorna uma lista de todas as músicas, serializadas como dicionários."""
        return [song.to_dict() for song in self.songs]

    def get_song_by_filename(self, filename):
        """Encontra um objeto de música pelo seu nome de arquivo."""
        for song in self.songs:
            if song.filename == filename:
                return song
        return None

# --- Configuração da Aplicação Flask ---
app = Flask(__name__, static_folder=None) # Não precisamos de uma pasta estática para esta configuração
library = MusicLibrary(music_folder='music')

# --- Endpoints da API ---

@app.route('/')
def index():
    """Serve o arquivo HTML principal."""
    return send_from_directory('.', 'spritefy_player.html')
    
@app.route('/api/songs', methods=['GET'])
def get_songs():
    """Endpoint da API para obter a lista de todas as músicas disponíveis."""
    return jsonify(library.get_all_songs())

@app.route('/api/stream/<path:filename>')
def stream_audio(filename):
    """Endpoint da API para transmitir um arquivo de áudio específico."""
    song = library.get_song_by_filename(filename)
    if not song:
        return "Música não encontrada", 404
        
    return send_from_directory(library.music_folder, filename)

# --- Endpoint para gerenciar Playlists (Criar, Atualizar, Listar) ---

@app.route('/api/playlists', methods=['GET', 'POST'])
def handle_playlists():
    """
    Endpoint para criar, atualizar e listar playlists.
    - GET: Retorna todas as playlists existentes.
    - POST: Cria uma nova playlist ou atualiza uma existente.
    """
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'name' not in data or 'songs' not in data:
            return jsonify({"error": "Dados inválidos. É necessário 'name' e 'songs'."}), 400
        
        playlist_name = data['name']
        song_filenames = data['songs']
        
        # --- LÓGICA DE CRIAÇÃO E ATUALIZAÇÃO ---
        library.playlists[playlist_name] = song_filenames
        library._save_playlists() # NEW: Save changes to the file
        
        print(f"Playlist '{playlist_name}' criada/atualizada com as músicas: {song_filenames}")
        
        return jsonify({"message": f"Playlist '{playlist_name}' salva com sucesso."}), 201

    elif request.method == 'GET':
        # Simplesmente retorna o dicionário completo de playlists.
        return jsonify(library.playlists)


if __name__ == '__main__':
    # Verifica se o diretório de músicas existe
    if not os.path.exists('music'):
        os.makedirs('music')
        print("Diretório 'music' criado. Por favor, adicione os seus ficheiros .mp3 lá.")
    
    # Executa a aplicação Flask
    app.run(debug=True, port=5000)
