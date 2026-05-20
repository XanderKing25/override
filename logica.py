import heapq
import random
import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
# cors_allowed_origins="*" es crucial para que Flutter se conecte sin problemas
socketio = SocketIO(app, cors_allowed_origins="*")

# --- BASE DE DATOS VISUAL (GITHUB RAW) ---
CARTAS_URLS = {
    "king_of_hearts2": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/king_of_hearts2.png",
    "queen_of_diamonds2": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/queen_of_diamonds2.png",
    "ace_of_spades2": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/ace_of_spades2.png",
    "ace_of_hearts": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/ace_of_hearts.png",
    "ace_of_diamonds": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/ace_of_diamonds.png",
    "ace_of_clubs": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/ace_of_clubs.png",
    "red_joker": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/red_joker.png",
    "black_joker": "https://raw.githubusercontent.com/XanderKing25/proyecto_parchado/main/img/Playing%20Cards/Playing%20Cards/PNG-cards-1.3/black_joker.png",
}

IDENTIDADES_POSIBLES = list(CARTAS_URLS.keys())

# --- BASE DE DATOS EN MEMORIA ---
jugadores = {}
salas = {}


# --- CANAL WEBSOCKET PARA FLUTTER ---
@socketio.on("join_private_room")
def on_join(data):
    """El cliente Flutter debe emitir este evento al conectarse usando su user_id"""
    user_id = data.get("user_id")
    if user_id:
        join_room(user_id)
        print(f"Terminal {user_id} enlazada al canal de notificaciones en tiempo real.")


# --- FUNCIONES DE SOPORTE ---


def limpiar_eliminados(nombre_sala):
    """Verifica si algún jugador se ha quedado sin suerte (suerte <= 0) y lo expulsa de la sala de inmediato."""
    if not nombre_sala or nombre_sala not in salas:
        return
    sala = salas[nombre_sala]
    eliminados = []
    sobrevivientes = []
    
    for j in list(sala["lista_circular"]):
        if jugadores.get(j, {}).get("suerte", 0) <= 0:
            jugadores[j]["estado_vital"] = "Eliminado"
            jugadores[j]["sala"] = None
            eliminados.append(j)
        else:
            sobrevivientes.append(j)
            
    sala["lista_circular"] = sobrevivientes
    
    for e in eliminados:
        socketio.start_background_task(
            notificar_privado,
            e,
            "💀 PROTOCOLO DE EXTERMINIO EJECUTADO.\nSignos vitales (Suerte): 0 o menor.\nHas sido purgado del sistema y expulsado de la sala permanentemente.",
            resultado={
                "tipo": "eliminado",
                "mensaje": "Has sido eliminado de la sala por quedarte sin suerte.",
            },
        )
        socketio.start_background_task(
            notificar_sala,
            nombre_sala,
            f"💀 El sujeto {jugadores[e]['nombre']} se ha quedado sin suerte y ha sido expulsado permanentemente."
        )

    # Si solo queda 1 jugador y la partida ya empezó, coronarlo ganador absoluto!
    if len(sala["lista_circular"]) == 1 and sala["estado"] != "LOBBY":
        ganador_unico = sala["lista_circular"][0]
        nombre_ganador = jugadores[ganador_unico]["nombre"]
        
        sala["pozo_acumulado"] = 0
        sala["turnos_jugados"] = 0
        sala["apuesta_maxima"] = 0
        sala["puntero_turno"] = 0
        sala["votantes"] = {}
        sala["estado"] = "LOBBY"
        jugadores[ganador_unico]["identidad"] = None
        
        msg_victoria = f"🏆 ¡EL SUJETO {nombre_ganador} ES EL ÚNICO SOBREVIVIENTE Y HA GANADO LA PARTIDA! 🏆"
        socketio.start_background_task(
            notificar_sala,
            nombre_sala,
            msg_victoria,
            resultado={
                "tipo": "ganador",
                "ganador": nombre_ganador,
                "mensaje": msg_victoria
            }
        )
    elif len(sala["lista_circular"]) == 0:
        sala["pozo_acumulado"] = 0
        sala["turnos_jugados"] = 0
        sala["apuesta_maxima"] = 0
        sala["puntero_turno"] = 0
        sala["votantes"] = {}
        sala["estado"] = "LOBBY"



def obtener_estado_juego(nombre_sala, user_id):
    if not nombre_sala or nombre_sala not in salas:
        return None
    sala = salas[nombre_sala]
    j = jugadores.get(user_id)
    turno_nombre = ""
    if sala["estado"] == "APUESTAS":
        if sala["lista_circular"] and sala["puntero_turno"] < len(sala["lista_circular"]):
            t_id_actual = sala["lista_circular"][sala["puntero_turno"]]
            turno_nombre = jugadores.get(t_id_actual, {}).get("nombre", "")
    elif sala["estado"] == "CONTRAATAQUE":
        if sala.get("duelo_activo"):
            defensor_id = sala["duelo_activo"]["defensor"]
            turno_nombre = jugadores.get(defensor_id, {}).get("nombre", "")
    elif sala["estado"] == "JUICIO":
        turno_nombre = "Votación"
    elif sala["estado"] == "JUEGO_EN_CURSO":
        turno_nombre = "Terminados"

    jugadores_activos = [
        jugadores[n]["nombre"] for n in sala["lista_circular"] if n in jugadores
    ]

    soy_defensor = False
    if (
        sala["estado"] == "CONTRAATAQUE"
        and sala.get("duelo_activo")
        and sala["duelo_activo"]["defensor"] == user_id
    ):
        soy_defensor = True

    acusado = ""
    if sala["estado"] == "JUICIO" and sala.get("candidato") in jugadores:
        acusado = jugadores[sala["candidato"]]["nombre"]

    return {
        "pozo": sala["pozo_acumulado"],
        "apuesta_maxima": sala["apuesta_maxima"],
        "estado": sala["estado"],
        "turno_de": turno_nombre,
        "suerte": j["suerte"] if j else 0,
        "identidad": j.get("identidad") if j else None,
        "url_imagen": CARTAS_URLS.get(j.get("identidad"))
        if j and j.get("identidad")
        else None,
        "jugadores_activos": jugadores_activos,
        "soy_defensor": soy_defensor,
        "acusado": acusado,
        "ha_atacado": j.get("ha_atacado", False) if j else False,
    }


def notificar_privado(user_id, mensaje, url_imagen=None, resultado=None):
    """Transmisión vía WebSocket directo a la app."""
    try:
        j = jugadores.get(user_id, {})
        estado = obtener_estado_juego(j.get("sala"), user_id)
        payload = {"mensaje": mensaje, "imagen": url_imagen, "game_state": estado}
        if resultado:
            payload["resultado"] = resultado
        socketio.emit("notificacion", payload, room=user_id)
    except Exception as e:
        print(f"Falla crítica de transmisión a {user_id}: {e}")


def notificar_sala(nombre_sala, mensaje, url_imagen=None, excluir=None, resultado=None):
    """Transmisión para todos los jugadores en la sala."""
    sala = salas.get(nombre_sala)
    if sala:
        for j in sala["lista_circular"]:
            if j != excluir:
                notificar_privado(j, mensaje, url_imagen, resultado=resultado)


def avanzar_turno(nombre_sala):
    sala = salas[nombre_sala]
    sala["turnos_jugados"] += 1

    if sala["turnos_jugados"] >= len(sala["lista_circular"]):
        sala["estado"] = "JUEGO_EN_CURSO"
        # Resetear ha_atacado para todos para la fase de combate libre
        for jid in sala["lista_circular"]:
            jugadores[jid]["ha_atacado"] = False
        msg_fin = "🔔 RONDA DE APUESTAS CERRADA.\nJuego en curso. El combate puede comenzar.\nAnfitrión usa !finalizar cuando sea momento de votar al ganador."
        # Notify ALL players that betting round is over → game is now active
        socketio.start_background_task(notificar_sala, nombre_sala, msg_fin)
        return (
            "Rueda completada. Fase de combate activa."
        )
    else:
        sala["puntero_turno"] = (sala["puntero_turno"] + 1) % len(
            sala["lista_circular"]
        )
        nuevo_turno = sala["lista_circular"][sala["puntero_turno"]]
        jugadores[nuevo_turno]["ha_atacado"] = False

        socketio.start_background_task(
            notificar_privado,
            nuevo_turno,
            f"⚠️ ES TU TURNO ⚠️\nSuerte Confidencial: {jugadores[nuevo_turno]['suerte']}\nIdentidad: {jugadores[nuevo_turno]['identidad']}\nAcción requerida.",
        )
        socketio.start_background_task(
            notificar_sala,
            nombre_sala,
            f"Turno transferido a: {jugadores[nuevo_turno]['nombre']}",
            None,
            nuevo_turno,
        )
        return f"Turno transferido a Sujeto: {jugadores[nuevo_turno]['nombre']}."


def aislar_top_3(nombre_sala):
    pass  # Ya no se usa, pero la dejamos por compatibilidad si es llamada en otro lado


# --- NÚCLEO REST API ---
@app.route("/api/comando", methods=["POST"])
def ejecutar_comando():
    datos = request.get_json()

    if not datos:
        return jsonify({"status": "error", "message": "Carga útil vacía."}), 400

    # Flutter debe enviar en el body algo como: {"user_id": "jugador_1", "comando": "!unirme Alex"}
    remitente = datos.get("user_id", "").strip()
    mensaje_entrante = datos.get("comando", "").lower().strip()

    if not remitente or not mensaje_entrante:
        return jsonify(
            {"status": "error", "message": "Faltan parámetros user_id o comando."}
        ), 400

    partes = mensaje_entrante.split(" ", 1)
    comando = partes[0]
    argumentos = partes[1].split(" ") if len(partes) > 1 else []
    arg_completo = partes[1] if len(partes) > 1 else ""

    def responder(texto, media=None, resultado=None):
        """Helper para estandarizar la respuesta JSON al instante"""
        res = {"status": "success", "message": texto}
        j = jugadores.get(remitente, {})
        estado = obtener_estado_juego(j.get("sala"), remitente)
        if estado:
            res["game_state"] = estado
        if media:
            res["media"] = media
        if resultado:
            res["resultado"] = resultado
        return jsonify(res)

    # 1. ACCESO Y LOBBY
    if comando == "!unirme":
        if not arg_completo:
            return responder("❌ Uso: !unirme [Nombre]")
        elif remitente not in jugadores:
            jugadores[remitente] = {
                "nombre": arg_completo,
                "suerte": 1000,
                "identidad": None,
                "estado_vital": "Activo",
                "ha_atacado": False,
                "sala": None,
            }
            return responder(f"Sujeto {arg_completo} registrado en la base de datos.")
        else:
            return responder("Su terminal ya posee una firma vital activa.")

    elif remitente not in jugadores:
        return responder("Acceso denegado. Requiere inscripción: !unirme [Nombre].")

    elif comando == "!crearsala":
        if jugadores[remitente]["sala"] is not None:
            return responder(
                "❌ Infracción. Su firma vital ya está vinculada a una sala activa."
            )
        elif arg_completo and arg_completo not in salas:
            salas[arg_completo] = {
                "lista_circular": [],
                "puntero_turno": 0,
                "turnos_jugados": 0,
                "pozo_acumulado": 0,
                "apuesta_maxima": 0,
                "estado": "LOBBY",
                "candidato": None,
                "votantes": {},
                "duelo_activo": None,
            }
            if jugadores[remitente].get("suerte", 0) <= 0:
                jugadores[remitente]["suerte"] = 1000
            jugadores[remitente]["estado_vital"] = "Activo"
            jugadores[remitente]["identidad"] = None
            jugadores[remitente]["ha_atacado"] = False
            jugadores[remitente]["sala"] = arg_completo
            salas[arg_completo]["lista_circular"].append(remitente)
            return responder(
                f"Sala '{arg_completo}' inicializada.\nAsignación automática: T-0 (Anfitrión).\nComando de ingreso para terceros: !unirsala {arg_completo}"
            )
        else:
            return responder(
                "Fallo de inicialización. Identificador de sala no disponible."
            )

    elif comando == "!unirsala":
        if jugadores[remitente]["sala"] is not None:
            return responder("❌ Infracción. Usted ya ocupa un asiento en otra sala.")
        elif arg_completo in salas:
            sala = salas[arg_completo]
            if sala["estado"] != "LOBBY":
                return responder("❌ Acceso denegado. La partida ya está en curso en esta sala.")
            if len(sala["lista_circular"]) >= 8:
                return responder(
                    "La sala ha alcanzado su límite operativo (8 sujetos). Acceso denegado."
                )
            if jugadores[remitente].get("suerte", 0) <= 0:
                jugadores[remitente]["suerte"] = 1000
            jugadores[remitente]["estado_vital"] = "Activo"
            jugadores[remitente]["identidad"] = None
            jugadores[remitente]["ha_atacado"] = False
            jugadores[remitente]["sala"] = arg_completo
            sala["lista_circular"].append(remitente)
            pos = len(sala["lista_circular"]) - 1
            socketio.start_background_task(
                notificar_sala,
                arg_completo,
                f"El sujeto {jugadores[remitente]['nombre']} se ha unido a la sala.",
                None,
                remitente,
            )
            return responder(
                f"Inyección exitosa. Posición asignada en la rueda: T-{pos}."
            )
        else:
            return responder("Sala inexistente.")

    # 2. INICIO Y REPARTO
    elif comando == "!repartir":
        mi_sala = jugadores[remitente]["sala"]
        if mi_sala and salas[mi_sala]["estado"] == "LOBBY":
            sala = salas[mi_sala]
            sala["estado"] = "APUESTAS"

            # SIEMPRE 2 jokers (red + black) sin importar el número de jugadores
            n_jugadores = len(sala["lista_circular"])
            if n_jugadores == 2:
                roles = ["red_joker", "black_joker"]
            else:
                cartas_normales = [c for c in IDENTIDADES_POSIBLES if "joker" not in c]
                relleno = []
                while len(relleno) < (n_jugadores - 2):
                    relleno.extend(cartas_normales)
                relleno = relleno[: (n_jugadores - 2)]
                roles = ["red_joker", "black_joker"] + relleno
            random.shuffle(roles)

            # 1. Asignar la identidad a todos los jugadores en la sala, y asegurar suerte válida
            for j in sala["lista_circular"]:
                if jugadores[j].get("suerte", 0) <= 0:
                    jugadores[j]["suerte"] = 1000
                jugadores[j]["estado_vital"] = "Activo"
                jugadores[j]["identidad"] = roles.pop() if roles else "default"

            # 2. Preparar el retorno del anfitrión de manera segura y definitiva
            # Si el anfitrión no está en la lista por algún motivo, devolvemos un error controlado en vez de un UnboundLocalError
            if remitente in sala["lista_circular"]:
                ident_host = jugadores[remitente]["identidad"]
                suerte_host = jugadores[remitente]["suerte"]
                url_img_host = CARTAS_URLS.get(ident_host)
                texto_carta_host = f"🃏 IDENTIDAD ASIGNADA 🃏\nSuerte actual: {suerte_host}\nVariable: {ident_host}.\nProteja su pantalla."
                texto_host = f"Niebla de Guerra desplegada.\n\n{texto_carta_host}\n\n⚠️ ES TU TURNO (T-0) ⚠️\nOpciones de riesgo: !apostar [monto], !igualar, !retirarse"
                respuesta_host = responder(texto_host, media=url_img_host)
            else:
                respuesta_host = responder("❌ Error: El anfitrión no se encuentra registrado en la rueda de la sala.")

            # 3. Notificar privadamente por SocketIO al resto de jugadores (ya con todos inicializados)
            for j in sala["lista_circular"]:
                if j != remitente:
                    ident_nombre = jugadores[j]["identidad"]
                    suerte_jugador = jugadores[j]["suerte"]
                    url_img = CARTAS_URLS.get(ident_nombre)
                    texto_carta = f"🃏 IDENTIDAD ASIGNADA 🃏\nSuerte actual: {suerte_jugador}\nVariable: {ident_nombre}.\nProteja su pantalla."
                    socketio.start_background_task(
                        notificar_privado, j, texto_carta, url_img
                    )

            return respuesta_host
        else:
            return responder(
                "Comando denegado. La mesa no está preparada o no se encuentra en LOBBY."
            )

    # 3. MOTOR ECONÓMICO (APUESTAS)
    elif comando in ["!apostar", "!igualar", "!retirarse"]:
        mi_sala = jugadores[remitente]["sala"]
        if not mi_sala:
            return responder("No estás en ninguna sala.")
        sala = salas[mi_sala]

        if sala["estado"] != "APUESTAS":
            return responder("Operación económica bloqueada en el estado actual.")

        turno_actual = sala["lista_circular"][sala["puntero_turno"]]
        if remitente != turno_actual:
            return responder("Infracción de secuencia. Silencio en la sala.")

        if comando == "!retirarse":
            multa = max(0, int(jugadores[remitente]["suerte"] * 0.5))
            jugadores[remitente]["suerte"] = max(0, jugadores[remitente]["suerte"] - multa)
            jugadores[remitente]["estado_vital"] = "Retirado"
            socketio.start_background_task(
                notificar_sala,
                mi_sala,
                f"{jugadores[remitente]['nombre']} huyó acobardado.",
                None,
                remitente,
            )
            status = avanzar_turno(mi_sala)
            return responder(
                f"Cobardía registrada. Multa del 50% aplicada (-{multa} suerte).\n{status}"
            )
        else:
            monto = 0
            if comando == "!apostar":
                try:
                    monto = int(argumentos[0])
                except:
                    return responder("Sintaxis requerida: !apostar [cantidad]")

                if monto <= 0:
                    return responder("❌ La apuesta debe ser mayor que cero.")

                if monto < sala["apuesta_maxima"]:
                    return responder(
                        f"Apuesta denegada. La apuesta actual es de {sala['apuesta_maxima']}. Debes usar !igualar o !retirarse."
                    )
            else:  # !igualar
                monto = sala["apuesta_maxima"]

            if monto > jugadores[remitente]["suerte"]:
                return responder(
                    f"❌ Operación rechazada. No posees suficiente suerte (Tu suerte: {jugadores[remitente]['suerte']}). Debes retirarte (!retirarse)."
                )

            jugadores[remitente]["suerte"] = max(0, jugadores[remitente]["suerte"] - monto)
            sala["pozo_acumulado"] += monto
            if monto > sala["apuesta_maxima"]:
                sala["apuesta_maxima"] = monto

            jugadores[remitente]["ha_atacado"] = True

            accion_txt = (
                f"apostó {monto}" if comando == "!apostar" else "igualó la apuesta"
            )
            socketio.start_background_task(
                notificar_sala,
                mi_sala,
                f"{jugadores[remitente]['nombre']} {accion_txt}.",
                None,
                remitente,
            )

            status = avanzar_turno(mi_sala)
            return responder(f"Transacción confirmada. Pozo encriptado.\n{status}")

    # 4. SISTEMA DE COMBATE (DUELO Y CONTRAATAQUE)
    elif comando == "!duelo":
        mi_sala = jugadores[remitente]["sala"]
        if not mi_sala:
            return responder("No estás en una sala.")
        sala = salas[mi_sala]

        if sala["estado"] not in ["JUEGO_EN_CURSO", "APUESTAS"]:
            return responder("Protocolo ofensivo bloqueado. Solo disponible durante el juego en curso.")

        if len(sala["lista_circular"]) <= 2:
            return responder(
                "Protocolo ofensivo bloqueado. En escenarios 1vs1 el robo de identidad está deshabilitado. Solo la asfixia económica decidirá al ganador."
            )
        elif sala["estado"] == "APUESTAS" and remitente != sala["lista_circular"][sala["puntero_turno"]]:
            return responder("Acción ofensiva denegada. Espere su turno.")
        elif jugadores[remitente]["ha_atacado"]:
            return responder("Munición agotada para este ciclo.")
        elif len(argumentos) < 2:
            return responder("Sintaxis: !duelo [nombre_objetivo] [nombre_carta]")
        else:
            obj_nom = " ".join(argumentos[:-1]).lower()
            carta_adiv = argumentos[-1].lower()
            obj_id = next(
                (
                    n
                    for n in sala["lista_circular"]
                    if jugadores[n]["nombre"].lower() == obj_nom
                ),
                None,
            )
            if not obj_id:
                return responder("Objetivo no detectado en el radar.")
            elif "joker" in carta_adiv:
                return responder("❌ Operación denegada. Los Jokers son inmunes al robo directo. Convoca al Tribunal (!acusar) para exponerlos.")
            elif jugadores[obj_id]["identidad"].lower() == carta_adiv:
                robo = max(0, int(jugadores[obj_id]["suerte"] * 0.5))
                jugadores[obj_id]["suerte"] = max(0, jugadores[obj_id]["suerte"] - robo)
                jugadores[remitente]["suerte"] += robo
                jugadores[remitente]["ha_atacado"] = True
                
                # Notificar a toda la sala de la extracción exitosa
                msg = f"💀 EXTRACCIÓN EXITOSA. {jugadores[remitente]['nombre']} adivinó la identidad de {jugadores[obj_id]['nombre']} y le robó {robo} de suerte."
                socketio.start_background_task(notificar_sala, mi_sala, msg)
                
                # Limpiar eliminados inmediatamente
                limpiar_eliminados(mi_sala)
                
                return responder(
                    f"💀 EXTRACCIÓN EXITOSA. {robo} de suerte transferidos de {obj_nom}."
                )
            else:
                jugadores[remitente]["ha_atacado"] = True
                sala["estado"] = "CONTRAATAQUE"
                sala["duelo_activo"] = {"retador": remitente, "defensor": obj_id}
                
                # Notificar a toda la sala de que el contraataque está activo
                msg = f"⚔️ Fallo balístico de {jugadores[remitente]['nombre']} contra {jugadores[obj_id]['nombre']}.\n¡El objetivo ha sido autorizado para contraatacar!"
                socketio.start_background_task(notificar_sala, mi_sala, msg)
                
                return responder(
                    f"Fallo balístico. Objetivo {obj_nom} autorizado para ejecución inversa.\nEnvíe !contraataque [carta]."
                )

    elif comando == "!contraataque":
        mi_sala = jugadores[remitente]["sala"]
        sala = salas[mi_sala]

        if (
            sala["estado"] != "CONTRAATAQUE"
            or remitente != sala["duelo_activo"]["defensor"]
        ):
            return responder("Acción denegada por el sistema.")
        else:
            retador = sala["duelo_activo"]["retador"]
            carta_adiv = arg_completo.lower()
            respuesta_txt = ""

            if (
                "joker" in carta_adiv
                or jugadores[retador]["identidad"].lower() != carta_adiv
            ):
                respuesta_txt = (
                    "Contraataque fallido. Ambos sujetos sobreviven al enfrentamiento."
                )
            else:
                robo = max(0, int(jugadores[retador]["suerte"] * 0.5))
                jugadores[retador]["suerte"] = max(0, jugadores[retador]["suerte"] - robo)
                jugadores[remitente]["suerte"] += robo
                respuesta_txt = f"💥 REPRESALIA LETAL CONFIRMADA. {robo} de suerte arrebatados al retador original."

            sala["estado"] = "JUEGO_EN_CURSO"
            sala["duelo_activo"] = None
            
            # Notificar a toda la sala el resultado del contraataque
            socketio.start_background_task(notificar_sala, mi_sala, respuesta_txt)
            
            # Limpiar eliminados inmediatamente
            limpiar_eliminados(mi_sala)
            
            return responder(respuesta_txt)

    # 5. TRIBUNAL DE PURGA
    elif comando == "!acusar":
        mi_sala = jugadores[remitente]["sala"]
        if not mi_sala:
            return responder("No estás en una sala.")
        sala = salas[mi_sala]

        if sala["estado"] not in ["JUEGO_EN_CURSO", "APUESTAS"]:
            return responder("Tribunal bloqueado. Solo disponible durante el juego en curso.")

        if len(sala["lista_circular"]) <= 2:
            return responder(
                "Tribunal denegado. La purga requiere un mínimo de 3 firmas vitales para formar quórum. En un 1vs1, no hay jurado posible."
            )
        else:
            obj_nom = arg_completo.lower()
            obj_id = next(
                (
                    n
                    for n in sala["lista_circular"]
                    if jugadores[n]["nombre"].lower() == obj_nom
                ),
                None,
            )
            if obj_id:
                sala["estado"] = "JUICIO"
                sala["candidato"] = obj_id
                sala["votantes"] = {}
                # Notificar a TODOS para que abra el panel de votación
                socketio.start_background_task(
                    notificar_sala,
                    mi_sala,
                    f"⚖️ TRIBUNAL CONVOCADO contra {jugadores[obj_id]['nombre']}.\nTodos deben votar: !votar si / !votar no.",
                    None,
                    None,
                )
                return responder(
                    f"⚖️ TRIBUNAL CONVOCADO contra {jugadores[obj_id]['nombre']}.\nLa mesa debe dictar sentencia obligatoria."
                )
            else:
                return responder("Objetivo no detectado en el radar de la sala.")

    elif (
        comando == "!votar"
        and salas[jugadores[remitente]["sala"]]["estado"] == "JUICIO"
    ):
        mi_sala = jugadores[remitente]["sala"]
        sala = salas[mi_sala]

        # El acusado no puede votar en su propio juicio
        if remitente == sala["candidato"]:
            return responder("❌ Operación rechazada. El acusado no tiene derecho a voto en su propio tribunal.")

        sala["votantes"][remitente] = arg_completo.lower()

        votantes_validos = [j for j in sala["lista_circular"] if j != sala["candidato"]]
        faltan = len(votantes_validos) - len(sala["votantes"])
        if faltan > 0:
            return responder(f"Voto registrado. Faltan {faltan} firmas para proceder.")
        else:
            votos_si = sum(1 for v in sala["votantes"].values() if v in ["si", "sí"])
            acusado = sala["candidato"]
            respuesta_txt = ""

            if votos_si <= len(votantes_validos) / 2:
                respuesta_txt = "Quórum insuficiente. Tribunal disuelto sin derramamiento de suerte."
            else:
                if "joker" in jugadores[acusado]["identidad"]:
                    robo = max(0, int(jugadores[acusado]["suerte"] * 0.5))
                    jugadores[acusado]["suerte"] = max(0, jugadores[acusado]["suerte"] - robo)

                    viejas_cartas = [
                        jugadores[j]["identidad"] for j in sala["lista_circular"]
                    ]
                    disponibles = [
                        c for c in IDENTIDADES_POSIBLES if c not in viejas_cartas
                    ]
                    jugadores[acusado]["identidad"] = (
                        random.choice(disponibles) if disponibles else "default"
                    )

                    regulares = [
                        j
                        for j in sala["lista_circular"]
                        if "joker" not in jugadores[j]["identidad"]
                    ]
                    if regulares:
                        nuevo_parasito = random.choice(regulares)
                        jugadores[nuevo_parasito]["identidad"] = "black_joker"
                        socketio.start_background_task(
                            notificar_privado,
                            nuevo_parasito,
                            "🦠 HAS SIDO INFECTADO. Eres el nuevo Joker.",
                        )

                    respuesta_txt = "🔥 PARÁSITO EXPUESTO. Se extirpó el 50% de su suerte. El Joker se ha reasignado en las sombras."
                else:
                    respuesta_txt = "⚠️ ERROR DE PURGA. Inocente condenado.\nImpuesto del 10% aplicado a todos los sujetos que votaron a favor."
                    for v_id, voto in sala["votantes"].items():
                        if voto == "si":
                            deduccion = max(0, int(jugadores[v_id]["suerte"] * 0.1))
                            jugadores[v_id]["suerte"] = max(0, jugadores[v_id]["suerte"] - deduccion)
            sala["estado"] = "JUEGO_EN_CURSO"
            sala["votantes"] = {}
            sala["candidato"] = None
            
            # Notificar a toda la sala de la resolución de la purga
            socketio.start_background_task(notificar_sala, mi_sala, respuesta_txt)
            
            # Limpiar eliminados inmediatamente
            limpiar_eliminados(mi_sala)
            
            return responder(respuesta_txt)

    # 6. CIERRE Y VEREDICTO DE SOMBRAS
    elif comando == "!finalizar":
        mi_sala = jugadores[remitente]["sala"]
        if not mi_sala or mi_sala not in salas:
            return responder("No estás en ninguna sala.")
        salas[mi_sala]["estado"] = "VEREDICTO"
        salas[mi_sala]["votantes"] = {}
        # Notify ALL players (incluyendo anfitrión) so their UI switches to VEREDICTO mode
        socketio.start_background_task(
            notificar_sala,
            mi_sala,
            "🏆 FASE FINAL INICIADA. Todos los sujetos deben emitir su veredicto: !ganador [nombre].",
            None,
            None,
        )
        return responder(
            "Fase de reto físico concluida. Decide el ganador tácticamente."
        )

    elif (
        comando == "!ganador"
        and jugadores[remitente]["sala"] in salas
        and salas[jugadores[remitente]["sala"]]["estado"] == "VEREDICTO"
    ):
        mi_sala = jugadores[remitente]["sala"]
        sala = salas[mi_sala]

        # Register this player's vote (any player can vote)
        sala["votantes"][remitente] = arg_completo.strip().lower()

        faltan = len(sala["lista_circular"]) - len(sala["votantes"])
        if faltan > 0:
            return responder(
                f"Voto registrado. Faltan {faltan} firma(s) para el veredicto."
            )

        # ── ALL PLAYERS HAVE VOTED ─────────────────────────────────────────
        # Only Jokers' votes decide the outcome
        jokers = [
            j
            for j in sala["lista_circular"]
            if jugadores[j].get("identidad") and "joker" in jugadores[j]["identidad"]
        ]
        votos_jokers = list({sala["votantes"].get(j, "") for j in jokers})
        pozo = sala["pozo_acumulado"]

        # ── CASO A: Consenso (todos los Jokers votaron lo mismo) ────────────
        if len(votos_jokers) == 1 and votos_jokers[0]:
            voto_consenso = votos_jokers[0]

            if voto_consenso == "ninguno":
                # ── NINGUNO: todos pierden 10% de su suerte actual ──────────
                for j in sala["lista_circular"]:
                    deduccion = max(0, int(jugadores[j]["suerte"] * 0.10))
                    jugadores[j]["suerte"] = max(0, jugadores[j]["suerte"] - deduccion)
                respuesta_txt = "⚠️ CONSENSO: NINGUNO. El pozo se evapora. Todos los sujetos pierden el 10% de su suerte."
                resultado_payload = {
                    "tipo": "ganador",
                    "ganador": "",
                    "mensaje": respuesta_txt,
                }

            else:
                # ── GANADOR: el consenso elige un ganador ───────────────────
                ganador_id = next(
                    (
                        n
                        for n in sala["lista_circular"]
                        if jugadores[n]["nombre"].lower() == voto_consenso
                    ),
                    None,
                )
                if not ganador_id:
                    # Invalid name voted — treat as disidencia
                    votos_jokers = ["invalid", ""]
                else:
                    ganador_nom = jugadores[ganador_id]["nombre"]
                    if len(sala["lista_circular"]) <= 2:
                        jugadores[ganador_id]["suerte"] += pozo
                        respuesta_txt = f"✅ CONSENSO ALCANZADO. {ganador_nom} se lleva el pozo de {pozo} suerte. Ronda terminada."
                    else:
                        impuesto = int(pozo * 0.20)
                        neto = pozo - impuesto
                        jugadores[ganador_id]["suerte"] += neto
                        for j in jokers:
                            jugadores[j]["suerte"] += (
                                int(impuesto / len(jokers)) if jokers else 0
                            )
                        respuesta_txt = f"✅ CONSENSO ALCANZADO. {ganador_nom} recibe {neto} suerte. Árbitros cobran {impuesto} de comisión. Ronda terminada."
                    resultado_payload = {
                        "tipo": "ganador",
                        "ganador": ganador_nom,
                        "pozo": pozo,
                        "mensaje": respuesta_txt,
                    }

            if len(votos_jokers) == 1:  # Still consensus after possible invalid check
                # ── Reset sala → LOBBY ───────────────────────────────────────
                sala["pozo_acumulado"] = 0
                sala["turnos_jugados"] = 0
                sala["apuesta_maxima"] = 0
                sala["puntero_turno"] = 0
                sala["votantes"] = {}
                sala["estado"] = "LOBBY"

                # Clear identities for next round
                for j in sala["lista_circular"]:
                    jugadores[j]["identidad"] = None

                # Garbage collector
                limpiar_eliminados(mi_sala)

                # Notify all survivors with resultado screen
                socketio.start_background_task(
                    notificar_sala,
                    mi_sala,
                    respuesta_txt,
                    None,
                    None,
                    resultado_payload,
                )

                return responder(respuesta_txt, resultado=resultado_payload)

        # ── CASO B: Disidencia (Jokers no se pusieron de acuerdo) ──────────
        fraude_txt = "⚠️ FRAUDE DETECTADO. Los árbitros no llegaron a un acuerdo. El pozo se evapora. Los Jokers caen a Cero Absoluto y son purgados del sistema."
        resultado_fraude = {"tipo": "fraude", "ganador": "", "mensaje": fraude_txt}

        # Jokers caen a CERO ABSOLUTO
        for j in jokers:
            jugadores[j]["suerte"] = 0

        # Garbage collector — elimina a jugadores con suerte <= 0
        limpiar_eliminados(mi_sala)

        # El pozo se evapora y la sala vuelve a LOBBY para nueva ronda
        sala["pozo_acumulado"] = 0
        sala["turnos_jugados"] = 0
        sala["apuesta_maxima"] = 0
        sala["puntero_turno"] = 0
        sala["votantes"] = {}
        sala["estado"] = "LOBBY"
        for j in sala["lista_circular"]:
            jugadores[j]["identidad"] = None

        # Notificar a todos con el resultado de fraude
        socketio.start_background_task(
            notificar_sala, mi_sala, fraude_txt, None, None, resultado_fraude
        )

        return responder(fraude_txt, resultado=resultado_fraude)


    # 7. UTILERÍA
    elif comando in ["!salas", "!mesas"]:
        if not salas:
            return responder(
                "📡 Radar vacío. No hay salas operativas en el servidor.\nInicie una con: !crearsala [Nombre]"
            )
        else:
            listado = "📋 DIRECTORIO DE SALAS 📋\n\n"
            for nombre, datos in salas.items():
                cantidad = len(datos["lista_circular"])
                estado = datos["estado"]
                if estado == "LOBBY":
                    listado += f"🟢 {nombre} | Sujetos: {cantidad} | {estado}\n"
                else:
                    listado += (
                        f"🔴 {nombre} | Sujetos: {cantidad} | {estado} (Cerrada)\n"
                    )
            listado += "\nPara entrar: !unirsala [Nombre]"
            return responder(listado)

    elif comando == "!jugadores":
        mi_sala = jugadores[remitente]["sala"]
        if not mi_sala:
            return responder("No te encuentras en ninguna sala.")
        else:
            sala = salas[mi_sala]
            nombres = [jugadores[j]["nombre"] for j in sala["lista_circular"]]
            return responder(
                f"Sujetos en la sala '{mi_sala}':\n"
                + "\n".join(f"- {n}" for n in nombres)
            )

    elif comando == "!mispuntos":
        return responder(
            f"Suerte confidencial: {jugadores[remitente]['suerte']} unidades."
        )

    elif comando == "!top":
        saldos = [info["suerte"] for info in jugadores.values() if "suerte" in info]
        top = heapq.nlargest(3, saldos)
        return responder(
            f"Top 3 Global:\n1. {top[0] if len(top) > 0 else 0}\n2. {top[1] if len(top) > 1 else 0}\n3. {top[2] if len(top) > 2 else 0}"
        )

    elif comando == "!salirsala":
        mi_sala = jugadores[remitente]["sala"]
        if mi_sala:
            sala = salas[mi_sala]
            if remitente in sala["lista_circular"]:
                if sala["estado"] != "LOBBY":
                    multa = max(0, int(jugadores[remitente]["suerte"] * 0.5))
                    jugadores[remitente]["suerte"] = max(0, jugadores[remitente]["suerte"] - multa)
                    sala["pozo_acumulado"] += multa
                    jugadores[remitente]["estado_vital"] = "Retirado"
                    socketio.start_background_task(
                        notificar_sala,
                        mi_sala,
                        f"{jugadores[remitente]['nombre']} huyó en plena ronda. Suerte confiscada al pozo.",
                        None,
                        remitente,
                    )

                sala["lista_circular"].remove(remitente)
                if not sala["lista_circular"]:
                    del salas[mi_sala]
                else:
                    if sala["estado"] == "LOBBY":
                        socketio.start_background_task(
                            notificar_sala,
                            mi_sala,
                            f"{jugadores[remitente]['nombre']} ha abandonado la sala.",
                            None,
                            remitente,
                        )
                    elif len(sala["lista_circular"]) == 1:
                        # Si solo queda 1 jugador, coronarlo ganador absoluto!
                        ganador_unico = sala["lista_circular"][0]
                        nombre_ganador = jugadores[ganador_unico]["nombre"]
                        
                        sala["pozo_acumulado"] = 0
                        sala["turnos_jugados"] = 0
                        sala["apuesta_maxima"] = 0
                        sala["puntero_turno"] = 0
                        sala["votantes"] = {}
                        sala["estado"] = "LOBBY"
                        jugadores[ganador_unico]["identidad"] = None
                        
                        msg_victoria = f"🏆 ¡EL SUJETO {nombre_ganador} ES EL ÚNICO SOBREVIVIENTE Y HA GANADO LA PARTIDA! 🏆"
                        socketio.start_background_task(
                            notificar_sala,
                            mi_sala,
                            msg_victoria,
                            resultado={
                                "tipo": "ganador",
                                "ganador": nombre_ganador,
                                "mensaje": msg_victoria
                            }
                        )

            jugadores[remitente]["sala"] = None
            return responder("Has abandonado la sala exitosamente.")
        return responder("No estás en ninguna sala.")

    elif comando == "!json_salas":
        import json

        lista = []
        for nombre, datos in salas.items():
            if datos["estado"] == "LOBBY" and len(datos["lista_circular"]) < 8:
                lista.append(
                    {"nombre": nombre, "cantidad": len(datos["lista_circular"])}
                )
        return responder(json.dumps(lista))

    # 8. MÓDULO DE ASISTENCIA (MENÚ)
    elif comando in ["!ayuda", "!menu"]:
        menu_supervivencia = (
            "⚙️ PROTOCOLO: SUERTE CIEGA ⚙️\n\n"
            "[SISTEMA BASE]\n"
            "• !unirme [Nombre] -> Registrar firma vital.\n"
            "• !crearsala [Nombre] -> Inicializar mesa.\n"
            "• !unirsala [Nombre] -> Ocupar asiento.\n"
            "• !salas -> Ver salas.\n"
            "• !jugadores -> Ver sujetos en la sala.\n\n"
            "[ECONOMÍA DE GUERRA]\n"
            "• !apostar [Cifra] -> Arriesgar suerte.\n"
            "• !igualar -> Pagar cuota máxima.\n"
            "• !retirarse -> Huir (Multa 50%).\n"
            "• !mispuntos -> Consultar saldo secreto.\n"
            "• !top -> Ver Top 3 anónimo.\n\n"
            "[EXTRACCIÓN Y PURGA]\n"
            "• !duelo [Nombre] [Carta] -> Intentar robar 50%.\n"
            "• !contraataque [Carta] -> Represalia.\n"
            "• !acusar [Nombre] -> Convocar tribunal.\n"
            "• !votar [si/no] -> Emitir sentencia.\n\n"
            "[CONTROL DE ANFITRIÓN]\n"
            "• !repartir -> Iniciar ronda y asignar cartas.\n"
            "• !finalizar -> Cerrar apuestas.\n"
            "• !ganador [Nombre] -> Resolución de Jokers."
        )
        return responder(menu_supervivencia)

    # 9. FALLBACK
    else:
        return responder(
            "Sintaxis no reconocida por el sistema. Ingrese !ayuda para leer el manual de supervivencia."
        )


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
