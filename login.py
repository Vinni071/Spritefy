from flask import Flask, request, jsonify
from flask_cors import CORS

# Inicializa o aplicativo Flask
app = Flask(__name__)
# Habilita o CORS para permitir requisições de outras origens (como seu arquivo HTML)
CORS(app)

# --- Em um aplicativo real, isso viria de um banco de dados ---
# Para este exemplo, vamos usar um dicionário simples como "banco de dados" de usuários.
# A chave é o nome de usuário e o valor é a senha.
VALID_CREDENTIALS = {
    "usuario": "senha123",
    "admin": "adminpass"
}

# Define a rota '/login' que aceita requisições do tipo POST
@app.route('/login', methods=['POST'])
def login():
    """
    Esta função é chamada quando o frontend envia dados para a URL /login.
    """
    # Pega os dados JSON enviados pelo frontend
    data = request.get_json()

    # Extrai o nome de usuário e a senha do JSON
    username = data.get('username')
    password = data.get('password')

    # Validação simples
    if not username or not password:
        return jsonify({"status": "error", "message": "Usuário e senha são obrigatórios!"}), 400

    # Verifica se o usuário existe e se a senha está correta
    if username in VALID_CREDENTIALS and VALID_CREDENTIALS[username] == password:
        # Se as credenciais estiverem corretas, retorna uma mensagem de sucesso
        print(f"Login bem-sucedido para o usuário: {username}")
        return jsonify({"status": "success", "message": "Login realizado com sucesso!"})
    else:
        # Se as credenciais estiverem incorretas, retorna uma mensagem de erro
        print(f"Tentativa de login falhou para o usuário: {username}")
        return jsonify({"status": "error", "message": "Usuário ou senha inválidos."}), 401 # 401 Unauthorized

# Permite que o script seja executado diretamente
if __name__ == '__main__':
    # Roda o servidor Flask em modo de depuração para facilitar o desenvolvimento
    # O servidor estará acessível em http://127.0.0.1:5000
    app.run(debug=True)
