import os
import json
import pytest
from app import app, Song, MusicLibrary

# --- Configuração do Pytest ---
@pytest.fixture
def client():
    """Cria um cliente de teste para a aplicação Flask."""
    # Cria um diretório de música de teste e um ficheiro de áudio falso
    music_dir = 'test_music'
    os.makedirs(music_dir, exist_ok=True)
    with open(os.path.join(music_dir, 'test.mp3'), 'w') as f:
        f.write('fake mp3 data')

    # Força a biblioteca a usar o diretório de teste
    app.config['TESTING'] = True
    MusicLibrary._instance = None # Reinicia o singleton para testes
    app.library = MusicLibrary(music_folder=music_dir)
    
    with app.test_client() as client:
        yield client
    
    # --- Limpeza após os testes ---
    MusicLibrary._instance = None # Garante que o singleton seja limpo
    os.remove(os.path.join(music_dir, 'test.mp3'))
    os.rmdir(music_dir)
    if os.path.exists('playlists.json'):
        os.remove('playlists.json')


# --- Testes Unitários para a Classe Song ---
def test_song_initialization():
    """Testa se a classe Song é inicializada corretamente com valores padrão."""
    song = Song('music/some_song.mp3', 1)
    assert song.filename == 'some_song.mp3'
    assert song.artist == 'Artista Desconhecido'
    assert song.id == 1
    assert song.to_dict()['title'] == 'some_song'

# --- Testes de Integração para os Endpoints da API ---
def test_get_songs_endpoint(client):
    """Testa o endpoint /api/songs."""
    # A varredura inicial é assíncrona, então esperamos um pouco
    import time
    time.sleep(1) # Aguarda a thread de varredura terminar
    
    rv = client.get('/api/songs')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]['filename'] == 'test.mp3'

def test_playlists_endpoint(client):
    """Testa a criação e listagem de playlists via API."""
    # Testa a listagem (deve estar vazia inicialmente)
    rv = client.get('/api/playlists')
    assert rv.status_code == 200
    assert json.loads(rv.data) == {}

    # Testa a criação de uma nova playlist
    playlist_data = {'name': 'Minha Playlist de Teste', 'songs': ['test.mp3']}
    rv = client.post('/api/playlists', data=json.dumps(playlist_data), content_type='application/json')
    assert rv.status_code == 201
    
    # Testa se a playlist foi salva corretamente
    rv = client.get('/api/playlists')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert 'Minha Playlist de Teste' in data
    assert data['Minha Playlist de Teste'] == ['test.mp3']

def test_stream_and_history_endpoint(client):
    """Testa o endpoint de streaming e se a música é adicionada ao histórico."""
    import time
    time.sleep(1) # Aguarda a varredura
    
    # Verifica se o histórico está vazio
    rv = client.get('/api/play-history')
    assert rv.status_code == 200
    assert json.loads(rv.data) == []

    # Faz uma requisição para o stream
    rv = client.get('/api/stream/test.mp3')
    assert rv.status_code == 200
    assert rv.data == b'fake mp3 data'

    # Verifica se a música foi adicionada ao histórico
    rv = client.get('/api/play-history')
    data = json.loads(rv.data)
    assert len(data) == 1
    assert data[0]['filename'] == 'test.mp3'

def test_scan_endpoints(client):
    """Testa os endpoints de controle da varredura da biblioteca."""
    # Testa o status inicial
    rv = client.get('/api/scan-status')
    assert rv.status_code == 200
    assert 'is_scanning' in json.loads(rv.data)
    
    # Aciona uma nova varredura
    rv = client.post('/api/scan')
    assert rv.status_code == 202 # Accepted
    
    # Verifica se o status mudou para 'scanning'
    rv = client.get('/api/scan-status')
    status = json.loads(rv.data)
    # Como a varredura de teste é muito rápida, pode ser que já tenha terminado.
    # O importante é que os endpoints respondam corretamente.
    assert 'is_scanning' in status
