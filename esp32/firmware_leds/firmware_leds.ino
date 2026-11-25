#define LED_ROJO     25
#define LED_VERDE    26
#define LED_AZUL     27
#define LED_AMARILLO 32

String bufferSerial = "";

void apagarLEDs() {
  digitalWrite(LED_ROJO, LOW);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_AZUL, LOW);
  digitalWrite(LED_AMARILLO, LOW);
}

void procesarMensaje(String mensaje) {
  mensaje.trim();

  if (mensaje == "ID:0") {
    apagarLEDs();
    Serial.println("OK: TODOS LOS LEDS APAGADOS");
  } else if (mensaje == "ID:1") {
    apagarLEDs();
    digitalWrite(LED_ROJO, HIGH);
    Serial.println("OK: PERSONA 1 - LED ROJO");
  } else if (mensaje == "ID:2") {
    apagarLEDs();
    digitalWrite(LED_VERDE, HIGH);
    Serial.println("OK: PERSONA 2 - LED VERDE");
  } else if (mensaje == "ID:3") {
    apagarLEDs();
    digitalWrite(LED_AZUL, HIGH);
    Serial.println("OK: PERSONA 3 - LED AZUL");
  } else if (mensaje == "ID:4") {
    apagarLEDs();
    digitalWrite(LED_AMARILLO, HIGH);
    Serial.println("OK: PERSONA 4 - LED AMARILLO");
  } else {
    Serial.print("ERROR: IDENTIFICADOR NO VALIDO: ");
    Serial.println(mensaje);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);

  pinMode(LED_ROJO, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AZUL, OUTPUT);
  pinMode(LED_AMARILLO, OUTPUT);

  apagarLEDs();
  Serial.println("ESP32 listo para recibir identificadores");
}

void loop() {
  while (Serial.available() > 0) {
    char caracter = (char)Serial.read();

    if (caracter == '\n') {
      procesarMensaje(bufferSerial);
      bufferSerial = "";
    } else if (caracter != '\r') {
      if (bufferSerial.length() < 32) {
        bufferSerial += caracter;
      } else {
        bufferSerial = "";
      }
    }
  }
}
