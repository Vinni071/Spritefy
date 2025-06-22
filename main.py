import flet as ft
import flet_audio as fa
import os
import glob
import time
import threading
import json
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from collections import deque

# --------------------------------------------------------------------------
# core/song.py
# --------------------------------------------------------------------------
class Song:
    """Representa um único arquivo de música com seus metadados."""
    def __init__(self, filepath, song_id):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.id = song_id
        self.title = os.path.splitext(self.filename)[0]
        self.artist = "Artista Desconhecido"
        self.album = "Álbum Desconhecido"
        self.duration = 0
        self.duration_str = "0:00"

        try:
            if filepath.lower().endswith('.mp3'):
                audio = MP3(filepath, ID3=EasyID3)
                self.title = audio.get('title', [self.title])[0]
                self.artist = audio.get('artist', [self.artist])[0]
                self.album = audio.get('album', [self.album])[0]
                self.duration = audio.info.length
                
                mins, secs = divmod(self.duration, 60)
                self.duration_str = f"{int(mins)}:{int(secs):02d}"
        except Exception:
            # Mantém os valores padrão se os metadados não puderem ser lidos
            pass

    def to_dict(self):
        """Serializa o objeto Song para um dicionário."""
        return {
            "id": self.id,
            "filepath": self.filepath,
            "filename": self.filename,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "duration_str": self.duration_str,
        }

    @classmethod
    def from_dict(cls, data):
        """Cria um objeto Song a partir de um dicionário."""
        song = cls(data['filepath'], data['id'])
        song.title = data['title']
        song.artist = data['artist']
        song.album = data['album']
        song.duration = data['duration']
        song.duration_str = data['duration_str']
        return song

# --------------------------------------------------------------------------
# core/library.py
# --------------------------------------------------------------------------
class MusicLibrary:
    """
    Gerencia a coleção de todas as músicas, aplicando o padrão Singleton.
    Isso garante que apenas uma instância da biblioteca exista na aplicação.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MusicLibrary, cls).__new__(cls)
        return cls._instance

    def __init__(self, music_folder='music', data_folder='data'):
        if not hasattr(self, 'initialized'):
            self.music_folder = music_folder
            self.data_folder = data_folder
            self.playlists_file = os.path.join(self.data_folder, 'playlists.json')
            
            self.songs = [] # Lista de objetos Song
            self.songs_by_filepath = {} # Tabela Hash para busca rápida
            self.playlists = {} # Dicionário de playlists
            
            self._ensure_folders_exist()
            self.initialized = True
            
    def _ensure_folders_exist(self):
        """Garante que os diretórios de música e dados existam."""
        os.makedirs(self.music_folder, exist_ok=True)
        os.makedirs(self.data_folder, exist_ok=True)
        
    def scan_songs(self, on_scan_complete=None):
        """
        Verifica o diretório de músicas e preenche a lista de músicas.
        Roda em uma thread para não bloquear a UI.
        """
        def thread_target():
            print(f"Iniciando varredura de músicas em '{self.music_folder}'...")
            found_files = glob.glob(os.path.join(self.music_folder, '*.mp3'))
            
            new_songs = []
            songs_by_filepath = {}

            for index, filepath in enumerate(found_files):
                song = Song(filepath, index)
                new_songs.append(song)
                songs_by_filepath[filepath] = song
            
            self.songs = new_songs
            self.songs_by_filepath = songs_by_filepath
            
            # Após a varredura, carrega as playlists que podem depender das músicas encontradas
            self.load_playlists()

            print(f"Varredura concluída. {len(self.songs)} músicas encontradas.")
            if on_scan_complete:
                on_scan_complete()
        
        # Inicia a thread de varredura
        scan_thread = threading.Thread(target=thread_target)
        scan_thread.daemon = True
        scan_thread.start()

    def get_song_by_filepath(self, filepath):
        """Retorna um objeto Song pelo seu caminho de arquivo."""
        return self.songs_by_filepath.get(filepath)

    def save_playlists(self):
        """Serializa as playlists para um arquivo JSON."""
        # Salva apenas os filepaths das músicas, não o objeto Song inteiro
        playlists_to_save = {}
        for name, song_list in self.playlists.items():
            playlists_to_save[name] = [song.filepath for song in song_list]
        
        with open(self.playlists_file, 'w', encoding='utf-8') as f:
            json.dump(playlists_to_save, f, indent=4)
        print("Playlists salvas com sucesso.")

    def load_playlists(self):
        """Desserializa as playlists do arquivo JSON."""
        if not os.path.exists(self.playlists_file):
            return

        try:
            with open(self.playlists_file, 'r', encoding='utf-8') as f:
                playlists_from_file = json.load(f)
            
            # Reconstrói as playlists com objetos Song
            self.playlists.clear()
            for name, filepaths in playlists_from_file.items():
                song_objects = []
                for fp in filepaths:
                    # Usa o dicionário de busca rápida
                    song = self.get_song_by_filepath(fp)
                    if song:
                        song_objects.append(song)
                self.playlists[name] = song_objects
            print("Playlists carregadas.")
        except (json.JSONDecodeError, FileNotFoundError):
            self.playlists = {}
            print("Não foi possível carregar as playlists ou o arquivo não existe.")
            
    def create_or_update_playlist(self, name, songs):
        """Cria ou atualiza uma playlist e a salva."""
        self.playlists[name] = songs
        self.save_playlists()

    def get_playlist(self, name):
        """Retorna uma lista de músicas de uma playlist específica."""
        return self.playlists.get(name, [])

# --------------------------------------------------------------------------
# core/player.py
# --------------------------------------------------------------------------
class Player:
    """
    Gerencia o estado e os controles de reprodução de áudio.
    Implementa o padrão Observer (Subject). A UI (Observer) se inscreve
    para receber notificações de mudança de estado.
    """
    def __init__(self, library):
        self.library = library
        self.audio = fa.Audio(autoplay=False) # Componente de áudio do pacote flet_audio
        
        # Estado do Player
        self.current_song = None
        self.is_playing = False
        
        # Estruturas de Dados
        self.playback_queue = deque() # Fila para próximas músicas
        self.history = [] # Pilha para histórico
        
        # Callbacks do padrão Observer
        self.observers = {
            "song_change": [],
            "play_pause": [],
        }

    def subscribe(self, event_type, observer_func):
        """Adiciona um observer (callback) para um evento."""
        if event_type in self.observers:
            self.observers[event_type].append(observer_func)

    def _notify(self, event_type, *args, **kwargs):
        """Notifica todos os observers registrados para um evento."""
        for observer_func in self.observers[event_type]:
            observer_func(*args, **kwargs)

    def load_playlist(self, songs):
        """Carrega uma lista de músicas na fila de reprodução."""
        self.playback_queue.clear()
        self.playback_queue.extend(songs)

    def play(self, song=None):
        """Toca uma música específica ou a próxima da fila."""
        if song:
            # Se uma música específica for fornecida, coloca ela como a próxima
            if song in self.playback_queue:
                while self.playback_queue[0] != song:
                    self.playback_queue.rotate(-1)
            else:
                self.playback_queue.appendleft(song)

        if not self.playback_queue:
            print("Fila de reprodução vazia.")
            return

        if self.current_song:
            self.history.append(self.current_song)

        self.current_song = self.playback_queue.popleft()
        
        self.audio.src = self.current_song.filepath
        self.audio.play()
        self.is_playing = True
        
        self._notify("song_change", self.current_song)
        self._notify("play_pause", self.is_playing)

    def resume(self):
        """Continua a reprodução da música atual."""
        if self.current_song:
            self.audio.resume()
            self.is_playing = True
            self._notify("play_pause", self.is_playing)

    def pause(self):
        """Pausa a reprodução da música atual."""
        self.audio.pause()
        self.is_playing = False
        self._notify("play_pause", self.is_playing)

    def next(self):
        """Toca a próxima música da fila."""
        if self.playback_queue:
            self.play() # play() já pega a próxima da fila
        else:
            print("Fim da fila de reprodução.")
            self.stop()
            
    def prev(self):
        """Toca a música anterior do histórico."""
        if not self.history:
            print("Não há músicas no histórico.")
            return

        # Devolve a música atual para o início da fila
        if self.current_song:
            self.playback_queue.appendleft(self.current_song)
        
        # Pega a última música do histórico e a toca
        prev_song = self.history.pop()
        self.playback_queue.appendleft(prev_song)
        self.play()

    def stop(self):
        """Para a reprodução e limpa o estado."""
        self.audio.pause() # Flet não tem stop, usamos pause
        self.current_song = None
        self.is_playing = False
        self._notify("song_change", None)
        self._notify("play_pause", self.is_playing)

    def set_volume(self, value):
        """Define o volume de reprodução (0.0 a 1.0)."""
        self.audio.volume = value / 100
        self.audio.update()

    def seek(self, position_ms):
        """Avança ou retrocede para uma posição na música."""
        self.audio.seek(position_ms)

# --------------------------------------------------------------------------
# UI Components
# --------------------------------------------------------------------------

class SongCard(ft.Container):
    """Cartão customizado para exibir uma música na lista."""
    def __init__(self, song, on_play_command):
        self.song = song
        self.on_play_command = on_play_command
        super().__init__(
            content=ft.Row(
                controls=[
                    ft.Icon(name=ft.Icons.MUSIC_NOTE_ROUNDED, color=ft.Colors.PURPLE_300),
                    ft.Column(
                        [
                            ft.Text(self.song.title, weight=ft.FontWeight.BOLD),
                            ft.Text(self.song.artist, size=12, color=ft.Colors.WHITE54),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.Text(self.song.duration_str, size=12, color=ft.Colors.WHITE54),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=10,
            border_radius=8,
            on_click=lambda _: self.on_play_command(self.song),
            ink=True,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        )

# --------------------------------------------------------------------------
# main.py - Aplicação Flet
# --------------------------------------------------------------------------

def main(page: ft.Page):
    
    # --- 1. Inicialização e Configuração ---
    page.title = "SoundWave Player"
    page.window_width = 800
    page.window_height = 720
    page.window_min_width = 600
    page.window_min_height = 600
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.PURPLE)
    page.padding = ft.padding.all(20)
    
    # Instanciando as classes do Core
    library = MusicLibrary()
    player = Player(library)
    
    # Adicionando o componente de áudio à página (é invisível)
    page.overlay.append(player.audio)

    # --- 2. Elementos da UI ---
    
    # Título
    header = ft.Text("Minhas Músicas", size=24, weight=ft.FontWeight.BOLD)
    
    # Barra de busca
    search_bar = ft.TextField(
        label="Buscar por título ou artista...",
        prefix_icon=ft.Icons.SEARCH,
        border_radius=20,
        filled=True,
        on_change=lambda e: filter_and_render_songs(),
    )
    
    # Lista de músicas
    songs_list_view = ft.ListView(expand=True, spacing=8)
    
    # Indicador de carregamento
    progress_ring = ft.ProgressRing(width=24, height=24, stroke_width=3)
    loading_container = ft.Row([progress_ring, ft.Text("Carregando músicas...")], visible=False, alignment=ft.MainAxisAlignment.CENTER)

    # --- Player Controls ---
    album_art_placeholder = "https://placehold.co/80x80/121212/FFFFFF?text=Sfy"
    album_art = ft.Image(src=album_art_placeholder, width=60, height=60, border_radius=8, fit=ft.ImageFit.COVER)
    track_title = ft.Text("Selecione uma música", weight=ft.FontWeight.BOLD)
    track_artist = ft.Text("SoundWave", color=ft.Colors.WHITE54)
    
    play_pause_button = ft.IconButton(icon=ft.Icons.PLAY_ARROW_ROUNDED, on_click=lambda e: toggle_play_pause_command(), icon_size=32)
    prev_button = ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, on_click=lambda e: player.prev())
    next_button = ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, on_click=lambda e: player.next())
    
    current_time_label = ft.Text("0:00")
    duration_label = ft.Text("0:00")
    progress_slider = ft.Slider(min=0, max=100, value=0, expand=True, on_change_end=lambda e: player.seek(int(e.control.value * 1000)))
    
    volume_slider = ft.Slider(width=100, min=0, max=100, value=100, on_change=lambda e: player.set_volume(e.control.value))

    player_controls = ft.Container(
        content=ft.Row(
            [
                album_art,
                ft.Column([track_title, track_artist], spacing=1, expand=True, tight=True),
                ft.Row([prev_button, play_pause_button, next_button], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([current_time_label, progress_slider, duration_label], expand=True, alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([ft.Icon(ft.Icons.VOLUME_UP), volume_slider], alignment=ft.MainAxisAlignment.END),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        padding=10,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE10),
        border=ft.border.only(top=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE))),
        border_radius=10,
    )
    
    # --- 3. Lógica e Comandos ---
    
    def on_scan_complete_callback():
        """Callback executado quando a varredura de músicas termina."""
        page.call_soon_threadsafe(lambda: set_loading_state(False))
        page.call_soon_threadsafe(filter_and_render_songs)

    def set_loading_state(is_loading):
        """Ativa/desativa o indicador de carregamento."""
        loading_container.visible = is_loading
        songs_list_view.visible = not is_loading
        if page.client_storage: # Evita erro se a página fechar antes da thread terminar
            page.update()

    def filter_and_render_songs():
        """Filtra as músicas baseado na busca e atualiza a lista."""
        search_term = search_bar.value.lower() if search_bar.value else ""
        filtered_songs = []
        if search_term:
            for song in library.songs:
                if search_term in song.title.lower() or search_term in song.artist.lower():
                    filtered_songs.append(song)
        else:
            filtered_songs = library.songs
        
        render_songs_to_list(filtered_songs)

    def render_songs_to_list(songs_to_render):
        """Renderiza uma lista de músicas na UI."""
        songs_list_view.controls.clear()
        for song in songs_to_render:
            songs_list_view.controls.append(SongCard(song, on_play_command=play_song_command))
        if page.client_storage:
            page.update()

    # Padrão Command: As funções a seguir encapsulam ações do usuário.
    def play_song_command(song: Song):
        """Comando para tocar uma música, carregando a lista atual na fila."""
        # Carrega a lista de músicas visível no momento como a fila de reprodução
        current_visible_songs = [card.song for card in songs_list_view.controls]
        player.load_playlist(current_visible_songs)
        player.play(song)
        
    def toggle_play_pause_command():
        """Comando para alternar entre play e pause."""
        if player.is_playing:
            player.pause()
        else:
            if player.current_song:
                player.resume()
            else:
                # Se nada estiver tocando, toca a primeira da lista visível
                if songs_list_view.controls:
                    first_song = songs_list_view.controls[0].song
                    play_song_command(first_song)

    # --- 4. Observers (Conexão UI <-> Core) ---
    
    def update_track_info_observer(song: Song):
        """Observer: Atualiza a informação da faixa no player."""
        if song:
            album_art.src = f"https://placehold.co/80x80/7e3ff2/FFFFFF?text={song.title[0]}"
            track_title.value = song.title
            track_artist.value = song.artist
            duration_label.value = song.duration_str
            progress_slider.max = song.duration
        else: # Limpa a UI se não houver música
            album_art.src = album_art_placeholder
            track_title.value = "Selecione uma música"
            track_artist.value = "SoundWave"
            duration_label.value = "0:00"
            progress_slider.max = 100
            progress_slider.value = 0
            current_time_label.value = "0:00"

        if page.client_storage:
            page.update()
        
    def update_play_pause_button_observer(is_playing: bool):
        """Observer: Atualiza o ícone do botão play/pause."""
        play_pause_button.icon = ft.Icons.PAUSE_ROUNDED if is_playing else ft.Icons.PLAY_ARROW_ROUNDED
        if page.client_storage:
            page.update()
        
    def update_progress_observer(e):
        """Observer: Atualiza a barra de progresso e o tempo atual."""
        position_ms = int(e.data)
        position_sec = position_ms / 1000
        if not progress_slider.on_change: # Não atualiza o slider se o usuário estiver arrastando
            progress_slider.value = position_sec
        mins, secs = divmod(position_sec, 60)
        current_time_label.value = f"{int(mins)}:{int(secs):02d}"
        if page.client_storage:
            page.update()

    # Registrando os observers no Player
    player.subscribe("song_change", update_track_info_observer)
    player.subscribe("play_pause", update_play_pause_button_observer)
    player.audio.on_position_changed = update_progress_observer
    player.audio.on_state_changed = lambda e: update_play_pause_button_observer(e.data == 'playing')
    player.audio.on_loaded = lambda e: update_track_info_observer(player.current_song)


    # --- 5. Layout da Página e Inicialização ---
    
    page.add(
        ft.Column(
            [
                header,
                search_bar,
                loading_container,
                songs_list_view,
            ],
            expand=True,
            spacing=20,
        ),
        player_controls,
    )
    
    # Inicia a varredura inicial de músicas
    set_loading_state(True)
    library.scan_songs(on_scan_complete=on_scan_complete_callback)


# Executando a aplicação
if __name__ == "__main__":
    ft.app(target=main)
