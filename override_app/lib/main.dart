import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:ui';
import 'package:socket_io_client/socket_io_client.dart' as IO;

enum FaseApp { login, lobby, sala }

void main() {
  runApp(const JuegoParchadoApp());
}

class JuegoParchadoApp extends StatelessWidget {
  const JuegoParchadoApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Override',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF09090B),
        primaryColor: const Color(0xFF8B5CF6),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF8B5CF6),
          secondary: Color(0xFF10B981),
          surface: Color(0xFF18181B),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF09090B),
          elevation: 0,
          centerTitle: true,
          scrolledUnderElevation: 0,
        ),
      ),
      home: const GestorPantallas(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class GestorPantallas extends StatefulWidget {
  const GestorPantallas({super.key});
  @override
  State<GestorPantallas> createState() => _GestorPantallasState();
}

class _GestorPantallasState extends State<GestorPantallas> {
  FaseApp faseActual = FaseApp.login;
  String miNombre = "";
  bool esAnfitrion = false;

  final String serverUrl = 'http://192.168.80.21:5000';
  IO.Socket? socket;

  // --- VARIABLES HUD Y CONTEXTO ---
  int _suerte = 0;
  int _pozo = 0;
  int _apuestaMaxima = 0;
  String _estadoSala = "LOBBY";
  String _turnoPerteneciente = "";
  String? _urlCartaPropia;

  List<String> _jugadoresActivos = [];
  bool _soyDefensor = false;
  String _acusado = "";
  bool _haAtacado = false;

  // Fases Locales Visuales (Caja Central)
  String _interfazLocal = "base";
  String _tempObjetivo = "";

  // Identidades del juego
  final Map<String, String> _nombresCartas = {
    "king_of_hearts2": "King of Hearts",
    "queen_of_diamonds2": "Queen of Diamonds",
    "ace_of_spades2": "Ace of Spades",
    "ace_of_hearts": "Ace of Hearts",
    "ace_of_diamonds": "Ace of Diamonds",
    "ace_of_clubs": "Ace of Clubs",
    "red_joker": "Red Joker",
    "black_joker": "Black Joker",
  };

  void _procesarEstadoJson(Map<String, dynamic>? data) {
    if (data == null) return;
    if (data.containsKey('game_state')) {
      final gs = data['game_state'];
      _pozo = gs['pozo'] ?? 0;
      _apuestaMaxima = gs['apuesta_maxima'] ?? 0;
      _estadoSala = gs['estado'] ?? "";
      _turnoPerteneciente = gs['turno_de'] ?? "";
      _suerte = gs['suerte'] ?? 0;
      _urlCartaPropia = gs['url_imagen'];

      if (gs['jugadores_activos'] != null) {
        _jugadoresActivos = List<String>.from(gs['jugadores_activos']);
      }
      _soyDefensor = gs['soy_defensor'] ?? false;
      _acusado = gs['acusado'] ?? "";
      _haAtacado = gs['ha_atacado'] ?? false;

      // Auto-Reset a tapete inicial con cada sync de estado, excepto si estamos nosotros haciendo UI local en APUESTAS
      if (_estadoSala != "APUESTAS" ||
          (_estadoSala == "APUESTAS" &&
              !(_interfazLocal.startsWith("ataque_") ||
                  _interfazLocal == "acusar"))) {
        _interfazLocal = "base";
      }
    }
  }

  Future<String?> enviarPeticion(String comando) async {
    try {
      final response = await http.post(
        Uri.parse('$serverUrl/api/comando'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'user_id': miNombre.isNotEmpty ? miNombre : "temp_user",
          'comando': comando,
        }),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _procesarEstadoJson(data);
        return data['message'];
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<void> enviarComandoSala(String comando) async {
    if (comando.isEmpty) return;
    try {
      final response = await http.post(
        Uri.parse('$serverUrl/api/comando'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'user_id': miNombre, 'comando': comando}),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          _procesarEstadoJson(data);
          _interfazLocal = "base"; // Reset gui after issuing order
        });
      }
    } catch (_) {}
  }

  void inicializarSocket() {
    socket = IO.io(serverUrl, <String, dynamic>{
      'transports': ['websocket'],
      'autoConnect': false,
    });
    socket!.connect();
    socket!.onConnect(
      (_) => socket!.emit('join_private_room', {'user_id': miNombre}),
    );
    socket!.on('notificacion', (data) {
      if (mounted && faseActual == FaseApp.sala) {
        setState(() {
          if (data['imagen'] != null && _urlCartaPropia == null) {
            _urlCartaPropia = data['imagen'];
          }
          _procesarEstadoJson(data);
        });
      }
    });
  }

  // --- TRANSICIONES Y ACCESOS ---

  void _ejecutarLogin(String nombre) async {
    if (nombre.trim().isEmpty) return;
    miNombre = nombre.trim();
    final res = await enviarPeticion("!unirme $miNombre");
    if (res != null &&
        (res.contains("registrado") || res.contains("ya posee"))) {
      setState(() {
        faseActual = FaseApp.lobby;
      });
      inicializarSocket();
    } else {
      miNombre = "";
    }
  }

  void _crearSala(String nombreSala) async {
    if (nombreSala.trim().isEmpty) return;
    final res = await enviarPeticion("!crearsala $nombreSala");
    if (res != null && res.contains("inicializada")) {
      setState(() {
        esAnfitrion = true;
        faseActual = FaseApp.sala;
        _urlCartaPropia = null;
      });
      enviarComandoSala("!jugadores");
    }
  }

  void _unirSala(String nombreSala) async {
    if (nombreSala.trim().isEmpty) return;
    final res = await enviarPeticion("!unirsala $nombreSala");
    if (res != null && res.contains("Inyección exitosa")) {
      setState(() {
        esAnfitrion = false;
        faseActual = FaseApp.sala;
        _urlCartaPropia = null;
      });
      enviarComandoSala("!jugadores");
    }
  }

  // --- PANELERÍA DE CONTEXTO VISUAL (Caja Central) ---

  Widget _buildListadoNombres(String titulo, Function(String) onSelect) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(15.0),
          child: Text(
            titulo,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 18,
              color: Colors.white,
              letterSpacing: 1.5,
            ),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: _jugadoresActivos.length,
            itemBuilder: (context, index) {
              final j = _jugadoresActivos[index];
              return ListTile(
                leading: const Icon(Icons.person, color: Colors.white30),
                title: Text(j, style: const TextStyle(fontSize: 16)),
                onTap: () => onSelect(j),
              );
            },
          ),
        ),
        TextButton(
          onPressed: () => setState(() => _interfazLocal = "base"),
          child: const Text(
            "CANCELAR",
            style: TextStyle(color: Colors.redAccent),
          ),
        ),
      ],
    );
  }

  Widget _buildListadoCartas(String titulo, Function(String) onSelect) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(15.0),
          child: Text(
            titulo,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 16,
              color: Colors.orangeAccent,
            ),
          ),
        ),
        Expanded(
          child: GridView.count(
            crossAxisCount: 2,
            childAspectRatio: 3,
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            padding: const EdgeInsets.all(10),
            children: _nombresCartas.entries.map((enf) {
              return OutlinedButton(
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.orangeAccent),
                ),
                onPressed: () => onSelect(enf.key),
                child: Text(
                  enf.value,
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              );
            }).toList(),
          ),
        ),
        TextButton(
          onPressed: () => setState(() => _interfazLocal = "base"),
          child: const Text(
            "CANCELAR",
            style: TextStyle(color: Colors.redAccent),
          ),
        ),
      ],
    );
  }

  Widget _buildTapeteDinamico() {
    // ESTADOS DEL SERVIDOR:
    if (_estadoSala == "JUICIO") {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.gavel, size: 80, color: Colors.redAccent),
            const SizedBox(height: 20),
            Text(
              "⚖️ VOTACIÓN DE PURGA EN CONTRA DE:\n\n${_acusado.toUpperCase()}",
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 18,
                color: Colors.white,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 40),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.red.shade900,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 40,
                      vertical: 20,
                    ),
                  ),
                  onPressed: () => enviarComandoSala("!votar si"),
                  child: const Text(
                    "SÍ (EXPULSAR)",
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ),
                ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blueGrey,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 40,
                      vertical: 20,
                    ),
                  ),
                  onPressed: () => enviarComandoSala("!votar no"),
                  child: const Text(
                    "NO",
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      );
    }
    if (_estadoSala == "VEREDICTO") {
      return _buildListadoNombres(
        "🏆 VOTA POR EL GANADOR TÁCTICO",
        (nom) => enviarComandoSala("!ganador $nom"),
      );
    }
    if (_estadoSala == "CONTRAATAQUE") {
      if (_soyDefensor) {
        return _buildListadoCartas(
          "¡TE HAN ATACADO! SELECCIONA EL IDENTIFICADOR DEL ATACANTE PARA DEFENDERTE:",
          (carta) => enviarComandoSala("!contraataque $carta"),
        );
      } else {
        return const Center(
          child: Text(
            "⚔️ DUELO EN PROGRESO...\nEspera a que los involucrados resuelvan.",
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.orangeAccent),
          ),
        );
      }
    }

    // ESTADOS LOCALES (INTERACCIONES PREVIAS A COMANDOS)
    if (_interfazLocal == "acusar") {
      return _buildListadoNombres(
        "¿A QUIÉN ARRASTRARÁS AL TRIBUNAL?",
        (nom) => enviarComandoSala("!acusar $nom"),
      );
    }
    if (_interfazLocal == "ataque_obj") {
      return _buildListadoNombres(
        "¿A QUIÉN ATACARÁS CUBIERTAMENTE?",
        (nom) => setState(() {
          _tempObjetivo = nom;
          _interfazLocal = "ataque_carta";
        }),
      );
    }
    if (_interfazLocal == "ataque_carta") {
      return _buildListadoCartas(
        "¿QUÉ IDENTIDAD POSEE $_tempObjetivo?",
        (carta) => enviarComandoSala("!duelo $_tempObjetivo $carta"),
      );
    }

    // ESTADO BASE (MOSAICOS DE CARTA O CENSOR)
    if (_urlCartaPropia != null) {
      return Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.5),
              blurRadius: 30,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: FadeInImage.assetNetwork(
          placeholder: '',
          image: _urlCartaPropia!,
          fit: BoxFit.contain,
          imageErrorBuilder: (_, _, _) => const Center(
            child: Icon(Icons.broken_image, color: Colors.white24, size: 60),
          ),
        ),
      );
    } else {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.style, size: 100, color: Colors.white.withOpacity(0.05)),
            const SizedBox(height: 20),
            const Text(
              "NIEBLA DE GUERRA\nEsperando despliegue de barajas...",
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white30,
                letterSpacing: 2,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      );
    }
  }

  Widget _buildSala() {
    bool esLobby = _estadoSala == "LOBBY";
    bool esApuestas = _estadoSala == "APUESTAS";
    bool esMiTurno =
        (_turnoPerteneciente.toUpperCase() == miNombre.toUpperCase());

    // BOTONES DISABLEABLES
    VoidCallback? fApuesta = (esApuestas && esMiTurno)
        ? () {
            String input = "";
            showDialog(
              context: context,
              builder: (_) => AlertDialog(
                backgroundColor: Colors.grey.shade900,
                title: const Text("Ingresar Cifra"),
                content: TextField(
                  onChanged: (v) => input = v,
                  keyboardType: TextInputType.number,
                ),
                actions: [
                  ElevatedButton(
                    onPressed: () {
                      Navigator.pop(context);
                      enviarComandoSala("!apostar $input");
                    },
                    child: const Text("Apostar"),
                  ),
                ],
              ),
            );
          }
        : null;
    VoidCallback? fIgualar = (esApuestas && esMiTurno)
        ? () => enviarComandoSala("!igualar")
        : null;
    VoidCallback? fHuir = (esApuestas && esMiTurno)
        ? () => enviarComandoSala("!retirarse")
        : null; // Label "Retirarse"

    VoidCallback? fDuelo =
        (esApuestas && esMiTurno && !_haAtacado && _suerte > 0)
        ? () => setState(() => _interfazLocal = "ataque_obj")
        : null;
    VoidCallback? fAcusar = (esApuestas && _suerte > 0)
        ? () => setState(() => _interfazLocal = "acusar")
        : null;

    VoidCallback? fRepartir = (esAnfitrion && esLobby)
        ? () => enviarComandoSala("!repartir")
        : null;
    // Solo puede finalizar durante apuestas, no en lobby y no si ya finalizó
    VoidCallback? fFinalizar =
        (esAnfitrion && _estadoSala != "LOBBY" && _estadoSala != "VEREDICTO")
        ? () => enviarComandoSala("!finalizar")
        : null;

    return Column(
      children: [
        // MARCADORES GLOBALES HUD
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xFF09090B),
            border: Border(
              bottom: BorderSide(
                color: const Color(0xFF8B5CF6).withOpacity(0.2),
                width: 1,
              ),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _MiniMarcador("POZO", "\$$_pozo", Colors.greenAccent),
              _MiniMarcador("ESTADO", _estadoSala, Colors.white),
              _MiniMarcador(
                "TURNO",
                _turnoPerteneciente.isEmpty ? "----" : _turnoPerteneciente,
                Colors.orangeAccent,
              ),
            ],
          ),
        ),

        // CAJA CENTRAL DINÁMICA (REEMPLAZA EL CHAT Y LA CARTA ÚNICA)
        Expanded(
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: _buildTapeteDinamico(),
          ),
        ),

        // BOTONES DE CONTROLES
        ClipRRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(
              padding: const EdgeInsets.fromLTRB(8, 16, 8, 20),
              decoration: BoxDecoration(
                color: const Color(0xFF09090B).withOpacity(0.8),
                border: Border(
                  top: BorderSide(
                    color: Colors.white.withOpacity(0.1),
                    width: 1,
                  ),
                ),
              ),
              child: SafeArea(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        vertical: 8,
                        horizontal: 20,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFF8B5CF6).withOpacity(0.1),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: const Color(0xFF8B5CF6).withOpacity(0.5),
                        ),
                      ),
                      child: Text(
                        "🪙 SUERTE RESTANTE: \$$_suerte",
                        style: const TextStyle(
                          color: Color(0xFFC4B5FD),
                          fontWeight: FontWeight.bold,
                          letterSpacing: 2,
                        ),
                      ),
                    ),
                    const SizedBox(height: 15),

                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      child: Row(
                        children: [
                          _ChipAccion(
                            label: "Apostar",
                            icon: Icons.attach_money,
                            color: const Color(0xFF10B981),
                            onTap: fApuesta,
                          ),
                          _ChipAccion(
                            label: "Igualar",
                            icon: Icons.balance,
                            color: const Color(0xFF64748B),
                            onTap: fIgualar,
                          ),
                          _ChipAccion(
                            label: "Retirarse",
                            icon: Icons.directions_run,
                            color: const Color(0xFFEF4444),
                            onTap: fHuir,
                          ),
                          _ChipAccion(
                            label: "Duelo",
                            icon: Icons.flash_on,
                            color: const Color(0xFFF59E0B),
                            onTap: fDuelo,
                          ),
                          _ChipAccion(
                            label: "Acusar",
                            icon: Icons.gavel,
                            color: Colors.blueAccent,
                            onTap: fAcusar,
                          ),
                        ],
                      ),
                    ),
                    if (esAnfitrion) ...[
                      const SizedBox(height: 15),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          _ChipAccion(
                            label: "Repartir",
                            icon: Icons.style,
                            color: const Color(0xFF8B5CF6),
                            onTap: fRepartir,
                          ),
                          _ChipAccion(
                            label: "Decidir Ganador",
                            icon: Icons.sports_score,
                            color: const Color(0xFFEC4899),
                            onTap: fFinalizar,
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  // --- RESTO DE VISTAS ---
  Widget _buildLogin() {
    String inputNombre = "";
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 40.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF8B5CF6).withOpacity(0.3),
                    blurRadius: 40,
                    spreadRadius: 10,
                  ),
                ],
              ),
              child: const Icon(
                Icons.security,
                size: 80,
                color: Color(0xFFA78BFA),
              ),
            ),
            const SizedBox(height: 30),
            ShaderMask(
              shaderCallback: (bounds) => const LinearGradient(
                colors: [Color(0xFFC4B5FD), Color(0xFF8B5CF6)],
              ).createShader(bounds),
              child: const Text(
                "OVERRIDE",
                style: TextStyle(
                  fontSize: 42,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 8,
                  color: Colors.white,
                ),
              ),
            ),
            const SizedBox(height: 60),
            TextField(
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                letterSpacing: 2,
              ),
              decoration: InputDecoration(
                hintText: "Identificador Clandestino",
                hintStyle: TextStyle(
                  color: Colors.white.withOpacity(0.3),
                  fontSize: 14,
                ),
                filled: true,
                fillColor: const Color(0xFF18181B),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: const BorderSide(
                    color: Color(0xFF8B5CF6),
                    width: 2,
                  ),
                ),
              ),
              onChanged: (val) => inputNombre = val,
            ),
            const SizedBox(height: 30),
            SizedBox(
              width: double.infinity,
              height: 60,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF8B5CF6),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20),
                  ),
                ),
                onPressed: () => _ejecutarLogin(inputNombre),
                child: const Text(
                  "INICIAR ENLACE",
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 2,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _mostrarSalasDisponibles() async {
    final res = await enviarPeticion("!json_salas");
    if (res == null) return;
    try {
      List<dynamic> salas = jsonDecode(res);
      if (!mounted) return;
      showModalBottomSheet(
        context: context,
        backgroundColor: const Color(0xFF18181B),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(30)),
        ),
        builder: (context) {
          if (salas.isEmpty) {
            return const Padding(
              padding: EdgeInsets.all(40),
              child: Text(
                "No hay salas públicas disponibles.",
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: Colors.grey),
              ),
            );
          }
          return Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 40,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.all(20.0),
                  child: Text(
                    "SELECCIÓN DE ENTORNO",
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 2,
                      color: Color(0xFF8B5CF6),
                    ),
                  ),
                ),
                Expanded(
                  child: ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    shrinkWrap: true,
                    itemCount: salas.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      final s = salas[index];
                      return ListTile(
                        tileColor: Colors.black26,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                        ),
                        leading: const Icon(
                          Icons.meeting_room,
                          color: Color(0xFFA78BFA),
                          size: 24,
                        ),
                        title: Text(
                          s['nombre'],
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                        subtitle: Text(
                          "Sujetos: ${s['cantidad']} / 8",
                          style: const TextStyle(
                            color: Colors.grey,
                            fontSize: 12,
                          ),
                        ),
                        onTap: () {
                          Navigator.pop(context);
                          _unirSala(s['nombre']);
                        },
                      );
                    },
                  ),
                ),
              ],
            ),
          );
        },
      );
    } catch (_) {}
  }

  void _pedirDato(
    String titulo,
    String hint,
    Function(String) onConfirm,
  ) async {
    String input = "";
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF18181B),
        title: Text(titulo),
        content: TextField(onChanged: (val) => input = val),
        actions: [
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              onConfirm(input);
            },
            child: const Text("Aceptar"),
          ),
        ],
      ),
    );
  }

  Widget _buildLobby() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            "Terminal activa:",
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 14,
            ),
          ),
          Text(
            miNombre.toUpperCase(),
            style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 40),
          _BotonAccionLobby(
            titulo: "CREAR SALA",
            subtitulo: "Inicializa entorno",
            icono: Icons.add_moderator,
            colorBase: const Color(0xFF10B981),
            onTap: () => _pedirDato("Nueva Sala", "Nombre", _crearSala),
          ),
          const SizedBox(height: 20),
          _BotonAccionLobby(
            titulo: "BUSCAR SALAS",
            subtitulo: "Infiltrarse",
            icono: Icons.radar,
            colorBase: const Color(0xFF3B82F6),
            onTap: _mostrarSalasDisponibles,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    String tituloAppBar = "Terminal";
    if (faseActual == FaseApp.lobby) tituloAppBar = "LOBBY PRINCIPAL";
    if (faseActual == FaseApp.sala) {
      tituloAppBar = esAnfitrion ? "MESA (ANFITRIÓN)" : "MESA VIRTUAL";
    }

    return Scaffold(
      appBar: faseActual == FaseApp.login
          ? null
          : AppBar(
              title: Text(
                tituloAppBar,
                style: const TextStyle(
                  fontWeight: FontWeight.w900,
                  letterSpacing: 2,
                  fontSize: 16,
                ),
              ),
              leading: faseActual == FaseApp.sala
                  ? IconButton(
                      icon: const Icon(
                        Icons.exit_to_app,
                        color: Colors.orangeAccent,
                      ),
                      onPressed: () {
                        enviarComandoSala("!salirsala");
                        setState(() => faseActual = FaseApp.lobby);
                      },
                    )
                  : null,
            ),
      body: SafeArea(
        child: faseActual == FaseApp.login
            ? _buildLogin()
            : faseActual == FaseApp.lobby
            ? _buildLobby()
            : _buildSala(),
      ),
    );
  }
}

// --- WIDGETS AUXILIARES ---

class _MiniMarcador extends StatelessWidget {
  final String label;
  final String valor;
  final Color colorClave;
  const _MiniMarcador(this.label, this.valor, this.colorClave);

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 10,
            color: Colors.white30,
            fontWeight: FontWeight.bold,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          valor.toUpperCase(),
          style: TextStyle(
            fontSize: 14,
            color: colorClave,
            fontWeight: FontWeight.w900,
          ),
        ),
      ],
    );
  }
}

class _BotonAccionLobby extends StatelessWidget {
  final String titulo, subtitulo;
  final IconData icono;
  final Color colorBase;
  final VoidCallback onTap;
  const _BotonAccionLobby({
    required this.titulo,
    required this.subtitulo,
    required this.icono,
    required this.colorBase,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(24),
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: colorBase.withOpacity(0.5)),
          color: colorBase.withOpacity(0.1),
        ),
        child: Row(
          children: [
            Icon(icono, color: colorBase, size: 32),
            const SizedBox(width: 20),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    titulo,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    subtitulo,
                    style: TextStyle(color: Colors.white.withOpacity(0.7)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChipAccion extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;

  const _ChipAccion({
    required this.label,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    bool d = onTap == null;
    Color c = d ? Colors.grey.shade600 : color;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4.0),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(30),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: d ? Colors.transparent : c.withOpacity(0.15),
              borderRadius: BorderRadius.circular(30),
              border: Border.all(
                color: d ? Colors.white12 : c.withOpacity(0.5),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, color: c, size: 18),
                const SizedBox(width: 8),
                Text(
                  label,
                  style: TextStyle(
                    color: c,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
