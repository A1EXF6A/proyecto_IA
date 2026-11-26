#define LED_ROJO        25
#define LED_VERDE       26
#define LED_AZUL        27
#define LED_AMARILLO    32
#define LED_DESCONOCIDO 33

String bufferSerial = "";

void apagarLEDs() {
  digitalWrite(LED_ROJO, LOW);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_AZUL, LOW);
  digitalWrite(LED_AMARILLO, LOW);
  digitalWrite(LED_DESCONOCIDO, LOW);
}

void procesarMensaje(String mensaje) {
  mensaje.trim();
  apagarLEDs();

  if (mensaje == "ID:0") {
    Serial.println("TODOS LOS LEDS APAGADOS");
  }
  else if (mensaje == "ID:1") {
    digitalWrite(LED_ROJO, HIGH);
    Serial.println("ALEXANDER LUISA - LED ROJO");
  }
  else if (mensaje == "ID:2") {
    digitalWrite(LED_VERDE, HIGH);
    Serial.println("ALEX GUACHI - LED VERDE");
  }
  else if (mensaje == "ID:3") {
    digitalWrite(LED_AZUL, HIGH);
    Serial.println("HEIDI VILLAVICENICIO - LED AZUL");
  }
  else if (mensaje == "ID:4") {
    digitalWrite(LED_AMARILLO, HIGH);
    Serial.println("STEVEN TOALA - LED AMARILLO");
  }
  else if (mensaje == "ID:5") {
    digitalWrite(LED_DESCONOCIDO, HIGH);
    Serial.println("PERSONA DESCONOCIDA - LED DE ALERTA");
  }
  else {
    Serial.println("IDENTIFICADOR NO VALIDO");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);

  pinMode(LED_ROJO, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AZUL, OUTPUT);
  pinMode(LED_AMARILLO, OUTPUT);
  pinMode(LED_DESCONOCIDO, OUTPUT);

  apagarLEDs();

  Serial.println("ESP32 LISTO");
}

void loop() {
  while (Serial.available() > 0) {
    char caracter = (char)Serial.read();

    if (caracter == '\n') {
      procesarMensaje(bufferSerial);
      bufferSerial = "";
    }
    else if (caracter != '\r') {
      if (bufferSerial.length() < 32) {
        bufferSerial += caracter;
      } else {
        bufferSerial = "";
      }
    }
  }
}
