from flask import Flask, render_template, request, redirect, jsonify, url_for
import json
import os
import requests
import servicos
from automacoes import automacoes_bp
from flask_socketio import SocketIO
import mqtt_cliente
import shared

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
# Atribui socketio ao shared, para uso no mqtt_cliente.py
shared.socketio = socketio

import time

@socketio.on("connect")
def ao_conectar():
    print("🔌 Cliente conectado ao Socket.IO")
    socketio.emit("mqtt_status", {"online": True})  # Emite assim que alguém se liga

# Registrar o blueprint
app.register_blueprint(automacoes_bp)

CONFIG_FILE = "config.json"
AUTOMACAO_FILE = "automacoes.json"
DISP_FILE = "dispositivos.json"


automa = []

@socketio.on('connect')
def handle_connect():
    from shared import mqtt_status
    print("🔌 Cliente Socket.IO conectado.")
    socketio.emit("mqtt_status", {"online": mqtt_status["online"]})


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return []  # Garante que sempre retornará uma lista vazia
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
        if isinstance(data, list):  # Verifica se o tipo retornado é uma lista
            return data
        else:
            return []  # Se não for uma lista, retorna uma lista vazia

def load_automacoes():       
    if not os.path.exists(AUTOMACAO_FILE):
        return []  # Garante que sempre retornará uma lista vazia
    with open(AUTOMACAO_FILE, "r") as f:
        data = json.load(f)
        if isinstance(data, list):  # Verifica se o tipo retornado é uma lista
            return data
        else:
            return []  # Se não for uma lista, retorna uma lista vazia

def obter_config_servicos():
    with open("servicos.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(layout):
    with open(CONFIG_FILE, "w") as f:
        json.dump(layout, f, indent=4)

def save_automacao(auto):
    with open(AUTOMACAO_FILE,"w") as f:
        json.dump(auto, f, indent=4)

@app.route("/")
def index():
    with open("config.json", "r") as f:
        layout = json.load(f)
        potencia_solar = 2500;  # valor real que leres do sistema
        print("Layout carregado:", layout)  # Para verificar o que está sendo retornado
    return render_template("index.html", layout=layout, potencia_solar=potencia_solar,mqtt_status="ON" if shared.mqtt_status["online"] else "OFF")
        #return render_template("index.html", layout=layout, potencia_solar=potencia_solar)

@app.route("/config", methods=["GET", "POST"])
def config():
    layout = load_config()
    with open("dispositivos.json", "r") as f:
        dispositivos = json.load(f)
    return render_template("config.html", layout=layout,dispositivos=dispositivos)

@app.route("/config/add_group", methods=["POST"])
def add_group():
    layout = load_config()
    title = request.form.get("group_title", "Novo Grupo")
    layout.append({"tipo": "grupo", "titulo": title, "conteudo": []})
    save_config(layout)
    return redirect("/config")

@app.route("/config/add_item", methods=["POST"])
def add_item():
    layout = load_config()  # Carrega o layout (uma lista de grupos)
    group_index = int(request.form["group_index"])  # Índice do grupo
    item_type = request.form["tipo"]

    # Construção do novo item
    new_item = {"tipo": item_type}

    if item_type == "botao":
        #new_item["nome"] = request.form["nome"]
        dispositivo_id = request.form["dispositivo_id"]
        # Carrega os dispositivos e busca o selecionado
        with open("dispositivos.json") as f:
            dispositivos = json.load(f)
        dispositivo = next((d for d in dispositivos if d["id"] == dispositivo_id), None)
        if dispositivo:
            new_item["nome"] = dispositivo["nome"]
            new_item["topico_comando"] = dispositivo["topico_comando"]
            #new_item["icone"] = dispositivo["icone"]
        else:
            print("Dispositivo não encontrado!")
    elif item_type == "toggle":
        new_item["nome"] = request.form["nome_toggle"]
        new_item["topico_estado"] = request.form["topico_estado"]
        new_item["topico_comando"] = request.form["topico_comando"]
        new_item["payload_ligar"] = request.form["payload_ligar"]
        new_item["payload_desligar"] = request.form["payload_desligar"]
    elif item_type == "camera":
        new_item["url"] = request.form["url"]
        new_item["width"] = int(request.form["width"])
        new_item["height"] = int(request.form["height"])
    elif item_type == "sensor":
        new_item["label"] = request.form["label"]
        new_item["value"] = request.form["value"]
    elif item_type == "slider":
        new_item["label"] = request.form["label"]
        new_item["min"] = int(request.form["min"])
        new_item["max"] = int(request.form["max"])
        new_item["value"] = int(request.form["value2"])
    elif item_type == "text":
        new_item["text"] = request.form["text"]

    # DEBUG: Verifica antes de adicionar
    print(f"Adicionar ao grupo {group_index}: {new_item}")

    # Garante que o índice é válido e a chave 'conteudo' existe
    if 0 <= group_index < len(layout) and "conteudo" in layout[group_index]:
        layout[group_index]["conteudo"].append(new_item)
    else:
        print("Erro: índice de grupo inválido ou grupo sem 'conteudo'.")

    save_config(layout)  # Agora salva corretamente

    return redirect("/config")


@app.route("/test_save")
def test_save():
    test_data = [{"tipo": "grupo", "titulo": "Teste", "conteudo": []}]
    save_config(test_data)
    return "Gravado"

@app.route("/msg")
def envia():
    servicos.enviar_mensagem_telegram("Olá")
    return "/"

@app.route('/atualizar_toggle', methods=['POST'])
def atualizar_toggle():
    layout_data = load_config()  # ✅ carrega o layout dinamicamente
    data = request.get_json()
    item_id = data.get("id")
    value = data.get("value")  # True ou False

    for grupo in layout_data:
        if grupo["tipo"] == "grupo":
            for item in grupo.get("conteudo", []):
                if item.get("tipo") == "toggle" and item.get("id") == item_id:
                    topico = item.get("topico_comando")
                    payload = item["payload_ligar"] if value else item["payload_desligar"]

                    if topico:
                        mqtt_cliente.publish(topico, payload)
                        print(f"Publicado no tópico {topico}: {payload}")
                        return jsonify({"status": "ok"})
                    else:
                        return jsonify({"status": "erro", "mensagem": "Tópico MQTT não definido"}), 400

    return jsonify({"status": "erro", "mensagem": "Item não encontrado"}), 404


# MQTT
@app.route("/enviar")
def enviar_mensagem():
    mqtt_cliente.mqtt_client.publish("cmnd/Luz_one/Power", "ON")
    return "Mensagem enviada!"

@app.route("/mqtt_status")
def mqtt_status_api():
    return jsonify(shared.mqtt_status)



@app.route("/temperatura")
def temperatura():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"erro": "Localização não fornecida"}), 400

    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m&timezone=auto"
        resposta = requests.get(url)
        dados = resposta.json()
        temperatura = dados["current"]["temperature_2m"]
        return jsonify({"temperatura": temperatura})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    
@app.route('/remover_grupo/<int:group_index>', methods=['POST'])
def remover_grupo(group_index):
    with open('config.json', 'r') as f:
        layout = json.load(f)

    if 0 <= group_index < len(layout):
        del layout[group_index]
        with open('config.json', 'w') as f:
            json.dump(layout, f, indent=2)
        return '', 200
    return 'Índice inválido', 400

@app.route('/remover_item/<int:group_index>/<int:item_index>', methods=['POST'])
def remover_item(group_index, item_index):
    with open('config.json', 'r') as f:
        layout = json.load(f)

    print(f"Remover pedido: grupo {group_index}, item {item_index}")
    print("Layout atual:", layout)

    try:
        layout[group_index]["conteudo"].pop(item_index)
        with open('config.json', 'w') as f:
            json.dump(layout, f, indent=2)
        return '', 204
    except (IndexError, KeyError) as e:
        print(f"Erro ao remover item: {e}")
        return "Item não encontrado", 404

@app.route('/obter_item/<int:group_index>/<int:item_index>')
def obter_item(group_index, item_index):
        with open('config.json', 'r') as f:
            layout = json.load(f)

        try:
            item = layout[group_index]["conteudo"][item_index]
            return jsonify(item)
        except (IndexError, KeyError):
            return "Item não encontrado", 404
        
@app.route('/editar_item/<int:group_index>/<int:item_index>', methods=['POST'])
def editar_item(group_index, item_index):
    dados = request.get_json()

    with open('config.json', 'r') as f:
        layout = json.load(f)

    try:
        item = layout[group_index]["conteudo"][item_index]

        # Atualiza apenas os campos fornecidos (exceto tipo)
        for chave in dados:
            if chave != "tipo":
                item[chave] = dados[chave]

        with open('config.json', 'w') as f:
            json.dump(layout, f, indent=2)

        return '', 204
    except (IndexError, KeyError) as e:
        return "Erro ao editar item", 400

#Editar ficheiro json
@app.route("/editar_layout", methods=["GET", "POST"])
def editar_layout():
    if request.method == "POST":
        novo_conteudo = request.form.get("conteudo")
        try:
            json_data = json.loads(novo_conteudo)  # validação do JSON
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            return redirect(url_for("editar_layout"))
        except Exception as e:
            return f"Erro ao salvar JSON: {e}"
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            conteudo = f.read()
        return render_template("editar_layout.html", conteudo=conteudo)
    
#-------------------------------------------------------------------------
# - - D I S P O S I T I V O S - -
def guardar_dispositivos(dispositivos):
    with open(DISP_FILE, "w") as f:
        json.dump(dispositivos, f, indent=2)

@app.route("/dispositivos", methods=["GET", "POST"])
def pagina_dispositivos():
    with open("dispositivos.json", "r") as f:
        dispositivos = json.load(f)

    if request.method == "POST":
        modo = request.form.get("modo")
        id_novo = request.form["id"]
        nome = request.form["nome"]
        tipo = request.form["tipo"]
        topico_estado = request.form["topico_estado"]
        topico_comando = request.form["topico_comando"]
        icone = request.form["icone"]

        if modo == "editar":
            id_original = request.form.get("id_original")
            for d in dispositivos:
                if d["id"] == id_original:
                    d.update({"id": id_novo, "nome": nome, "tipo": tipo, "topico_estado": topico_estado,"topico_comando":topico_comando, "icone": icone})
                    break
        else:  # adicionar
            dispositivos.append({
                "id": id_novo,
                "nome": nome,
                "tipo": tipo,
                "topico_estado": topico_estado,
                "topico_comando": topico_comando,
                "icone": icone
            })

        with open("dispositivos.json", "w") as f:
            json.dump(dispositivos, f, indent=2)

        
        #return redirect(url_for("pagina_dispositivos"))

    return render_template("dispositivos.html", dispositivos=dispositivos)

#-------------------------------------------------------------------------
@app.route('/servicos', methods=['GET', 'POST'])
def configurar_servicos():
    config_path = 'servicos.json'

    # Carregar config existente ou criar padrão
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        config = {}

    if request.method == 'POST':
        nova_config = {}

        for servico, campos in config.items():
            nova_config[servico] = {}
            for campo in campos:
                key = f"{servico}__{campo}"
                valor = request.form.get(key)

                # Converter para tipo original
                if isinstance(config[servico][campo], bool):
                    nova_config[servico][campo] = bool(request.form.get(key))
                elif isinstance(config[servico][campo], int):
                    nova_config[servico][campo] = int(valor or 0)
                else:
                    nova_config[servico][campo] = valor

        with open(config_path, 'w') as f:
            json.dump(nova_config, f, indent=4)

        return redirect('/servicos')

    return render_template('servicos.html', config=config)

@socketio.on("testar_evento")
def resposta():
    print("🧪 Recebido evento de teste do browser")
    shared.socketio.emit("mqtt_status", {"online": False})
   

if __name__ == "__main__":
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        mqtt_cliente.conectar()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

#Fim
