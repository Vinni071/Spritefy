import os
import glob
import json
import threading
from collections import deque
from flask import Flask, jsonify, send_from_directory, request
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

# --- 1. Programação Orientada a Objetos ---
# Classes coesas que representam as entidades principais do sistema.

class Song:
    """Representa um único arquivo de música com seus metadados."""
    def __init__(self, filepath, song_id):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.id = song_id
        # --- Valores Padrão ---
        self.title = os.path.splitext(self.filename)[0]
        self.artist = "Artista Desconhecido"
        self.album = "Álbum Desconhecido"
        self.duration = 0
        
        # --- 3. Manipulação de Arquivos e Serialização (Leitura de Metadados) ---
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

# --- 5. Padrão de Projeto: Singleton ---
# Garante que haverá apenas uma instância da biblioteca de músicas,
# centralizando o acesso e o estado dos dados.
class MusicLibrary:
    """Gerencia a coleção de músicas, playlists, fila e histórico."""
    _instance = None
    
    # --- 2. Estruturas de Dados ---
    # Usando uma variedade de estruturas de dados para diferentes finalidades.
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MusicLibrary, cls).__new__(cls)
        return cls._instance

    def __init__(self, music_folder='music'):
        if not hasattr(self, 'initialized'):
            self.music_folder = music_folder
            self.playlists_file = 'playlists.json'
            
            # Tabela Hash (dicionário) para busca rápida de músicas por nome de arquivo.
            self.songs_map = {}
            # Lista para manter a ordem das músicas.
            self.songs_list = []
            # Dicionário para armazenar as playlists.
            self.playlists = {}
            # Fila (deque) para gerenciar as próximas músicas a serem tocadas.
            self.play_queue = deque()
            # Pilha (lista) para manter o histórico de reprodução.
            self.play_history = []
            
            self.is_scanning = False
            self.scan_lock = threading.Lock() # Para garantir que apenas uma varredura ocorra por vez.

            self._load_playlists()
            self.scan_songs_async() # Inicia a primeira varredura de forma assíncrona.
            self.initialized = True
            
    def _load_playlists(self):
        """Carrega as playlists do arquivo JSON, se ele existir."""
        try:
            if os.path.exists(self.playlists_file):
                with open(self.playlists_file, 'r') as f:
                    self.playlists = json.load(f)
        except Exception as e:
            print(f"Erro ao carregar o arquivo de playlists: {e}")
            self.playlists = {}

    def _save_playlists(self):
        """Salva as playlists atuais no arquivo JSON (Serialização)."""
        try:
            with open(self.playlists_file, 'w') as f:
                json.dump(self.playlists, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar o arquivo de playlists: {e}")

    # --- 4. Programação Concorrente (Multithreading) ---
    def scan_songs_async(self):
        """Inicia a varredura de músicas em uma nova thread para não bloquear o servidor."""
        if self.is_scanning:
            return # Impede múltiplas varreduras simultâneas.
            
        scan_thread = threading.Thread(target=self._scan_songs_worker)
        scan_thread.start()

    def _scan_songs_worker(self):
        """O trabalho real de varredura que executa na thread."""
        with self.scan_lock:
            self.is_scanning = True
            print(f"Iniciando varredura de músicas no diretório '{self.music_folder}'...")
            
            temp_songs_list = []
            temp_songs_map = {}
            
            for index, filepath in enumerate(glob.glob(os.path.join(self.music_folder, '*.mp3'))):
                song = Song(filepath, index)
                temp_songs_list.append(song)
                temp_songs_map[song.filename] = song
            
            # Atualiza as estruturas de dados principais de forma atômica.
            self.songs_list = temp_songs_list
            self.songs_map = temp_songs_map
            
            print(f"Varredura concluída. {len(self.songs_list)} músicas encontradas.")
            self.is_scanning = False

    def get_scan_status(self):
        """Retorna o status atual da varredura da biblioteca."""
        return {"is_scanning": self.is_scanning, "song_count": len(self.songs_list)}

    def get_all_songs(self):
        """Retorna uma lista de todas as músicas."""
        return [song.to_dict() for song in self.songs_list]

    def get_song_by_filename(self, filename):
        """Encontra um objeto de música pelo seu nome de arquivo usando a tabela hash."""
        return self.songs_map.get(filename)
        
    def add_song_to_history(self, filename):
        """Adiciona uma música à pilha de histórico."""
        song = self.get_song_by_filename(filename)
        if song:
            # Para evitar duplicatas consecutivas no histórico
            if not self.play_history or self.play_history[-1]['filename'] != song.filename:
                self.play_history.append(song.to_dict())

# --- Configuração da Aplicação Flask ---
app = Flask(__name__, static_folder=None)
library = MusicLibrary(music_folder='music')

# --- Endpoints da API ---

@app.route('/')
def index():
    """Serve o arquivo HTML principal."""
    return send_from_directory('.', 'spritefy_player.html')
    
@app.route('/api/songs', methods=['GET'])
def get_songs():
    """Endpoint para obter a lista de todas as músicas disponíveis."""
    return jsonify(library.get_all_songs())

@app.route('/api/stream/<path:filename>')
def stream_audio(filename):
    """Endpoint para transmitir um arquivo de áudio e registrar no histórico."""
    song = library.get_song_by_filename(filename)
    if not song:
        return "Música não encontrada", 404
    
    library.add_song_to_history(filename)
    return send_from_directory(library.music_folder, filename)

@app.route('/api/playlists', methods=['GET', 'POST'])
def handle_playlists():
    """Endpoint para criar, atualizar e listar playlists."""
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'name' not in data or 'songs' not in data:
            return jsonify({"error": "Dados inválidos. É necessário 'name' e 'songs'."}), 400
        
        playlist_name = data['name']
        library.playlists[playlist_name] = data['songs']
        library._save_playlists()
        return jsonify({"message": f"Playlist '{playlist_name}' salva com sucesso."}), 201

    return jsonify(library.playlists)

# --- Novos Endpoints para Concorrência e Estruturas de Dados ---

@app.route('/api/scan', methods=['POST'])
def trigger_scan():
    """Endpoint para acionar uma nova varredura da biblioteca."""
    if library.is_scanning:
        return jsonify({"message": "Uma varredura já está em andamento."}), 429 # Too Many Requests
    library.scan_songs_async()
    return jsonify({"message": "Varredura da biblioteca iniciada em segundo plano."}), 202 # Accepted

@app.route('/api/scan-status', methods=['GET'])
def get_scan_status():
    """Endpoint para verificar o status da varredura."""
    return jsonify(library.get_scan_status())

@app.route('/api/play-history', methods=['GET'])
def get_play_history():
    """Endpoint para obter o histórico de reprodução (Pilha)."""
    # Retorna o histórico em ordem inversa (mais recente primeiro)
    return jsonify(list(reversed(library.play_history)))

if __name__ == '__main__':
    if not os.path.exists('music'):
        os.makedirs('music')
        print("Diretório 'music' criado. Por favor, adicione os seus ficheiros .mp3 lá.")
    
    app.run(debug=True, port=5000)
