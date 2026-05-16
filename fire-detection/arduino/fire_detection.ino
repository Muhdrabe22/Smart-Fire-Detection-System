/*
 * Smart Fire Detection System - Arduino Firmware
 * Hardware: Arduino Uno + Ethernet Shield (W5100)
 * Sensors:  MQ-2 (Smoke/Gas) + DHT22 (Temperature/Humidity)
 *
 * Wiring:
 *   MQ-2  VCC -> 5V | GND -> GND | AOUT -> A0
 *   DHT22 VCC -> 5V | GND -> GND | DATA -> D2 (with 10k pull-up)
 *   Buzzer             -> D7
 *   LED (Red/Alert)    -> D8
 *   LED (Green/Normal) -> D9
 */

#include <SPI.h>
#include <Ethernet.h>
#include <DHT.h>
#include <ArduinoJson.h>

// ─── CONFIG ────────────────────────────────────────────────────────────────
#define DEVICE_ID       "SENSOR-NODE-01"
#define DEVICE_LOCATION "Server Room"

// Sensor Pins
#define MQ2_PIN       A0
#define DHT_PIN       2
#define DHT_TYPE      DHT22   // Change to DHT11 if using DHT11
#define BUZZER_PIN    7
#define LED_RED_PIN   8
#define LED_GREEN_PIN 9

// Alert Thresholds (tune these for your environment)
#define SMOKE_THRESHOLD_WARN   300   // ADC value (0-1023)
#define SMOKE_THRESHOLD_DANGER 600
#define TEMP_THRESHOLD_WARN    40.0  // °C
#define TEMP_THRESHOLD_DANGER  55.0
#define GAS_PPM_WARN           200
#define GAS_PPM_DANGER         500

// Network — update these for your setup
byte mac[]     = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
IPAddress ip(192, 168, 1, 177);          // Arduino static IP
IPAddress server(192, 168, 1, 100);      // Flask server IP
const int SERVER_PORT = 5000;

// Intervals
const unsigned long SEND_INTERVAL    = 5000;   // 5s normal reporting
const unsigned long ALERT_INTERVAL   = 2000;   // 2s during alert
const unsigned long WARMUP_TIME      = 30000;  // 30s MQ-2 warmup

// ─── GLOBALS ───────────────────────────────────────────────────────────────
EthernetClient client;
DHT dht(DHT_PIN, DHT_TYPE);

unsigned long lastSendTime  = 0;
unsigned long startupTime   = 0;
bool          sensorWarmedUp = false;
int           alertLevel    = 0;   // 0=normal, 1=warning, 2=danger

// ─── SETUP ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  while (!Serial) {}

  pinMode(BUZZER_PIN,    OUTPUT);
  pinMode(LED_RED_PIN,   OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);

  // Startup indicator
  digitalWrite(LED_GREEN_PIN, HIGH);
  Serial.println(F("=== Smart Fire Detection System ==="));
  Serial.print(F("Device ID: ")); Serial.println(DEVICE_ID);

  // Init Ethernet
  Serial.println(F("Initializing Ethernet..."));
  if (Ethernet.begin(mac) == 0) {
    Serial.println(F("DHCP failed, using static IP"));
    Ethernet.begin(mac, ip);
  }
  delay(1000);
  Serial.print(F("IP: ")); Serial.println(Ethernet.localIP());

  // Init DHT
  dht.begin();

  // MQ-2 warmup
  Serial.println(F("Warming up MQ-2 sensor (30s)..."));
  startupTime = millis();
  for (int i = 30; i > 0; i--) {
    Serial.print(i); Serial.print(F("s "));
    blinkLED(LED_GREEN_PIN, 500);
    delay(500);
  }
  Serial.println();
  sensorWarmedUp = true;
  Serial.println(F("System ready!"));
}

// ─── MAIN LOOP ─────────────────────────────────────────────────────────────
void loop() {
  unsigned long now      = millis();
  unsigned long interval = (alertLevel > 0) ? ALERT_INTERVAL : SEND_INTERVAL;

  if (now - lastSendTime >= interval) {
    lastSendTime = now;

    // Read sensors
    float temperature = dht.readTemperature();
    float humidity    = dht.readHumidity();
    int   smokeRaw    = analogRead(MQ2_PIN);
    float smokePPM    = convertToPPM(smokeRaw);
    bool  dhtValid    = !isnan(temperature) && !isnan(humidity);

    // Debug output
    Serial.println(F("--- Sensor Readings ---"));
    Serial.print(F("Temp: "));     Serial.print(temperature); Serial.println(F(" °C"));
    Serial.print(F("Humidity: ")); Serial.print(humidity);    Serial.println(F(" %"));
    Serial.print(F("Smoke Raw: ")); Serial.println(smokeRaw);
    Serial.print(F("Smoke PPM: ")); Serial.println(smokePPM);

    // Evaluate alert level
    alertLevel = evaluateAlert(smokeRaw, smokePPM, temperature);
    Serial.print(F("Alert Level: ")); Serial.println(alertLevel);

    // Activate local alerts
    handleLocalAlert(alertLevel);

    // Send to Flask server
    if (dhtValid) {
      sendSensorData(temperature, humidity, smokeRaw, smokePPM, alertLevel);
    } else {
      Serial.println(F("DHT read failed — skipping send"));
    }
  }

  Ethernet.maintain();
}

// ─── FUNCTIONS ─────────────────────────────────────────────────────────────

// Convert MQ-2 ADC value to approximate PPM (calibrated for LPG/Smoke)
float convertToPPM(int rawValue) {
  // Simple linear mapping — replace with Rs/Ro curve for accuracy
  // MQ-2 typical: clean air Rs/Ro ~9.8, danger ~1
  float voltage = rawValue * (5.0 / 1023.0);
  float ppm = (voltage / 5.0) * 1000.0;
  return ppm;
}

// Determine alert level from sensor values
int evaluateAlert(int smokeRaw, float smokePPM, float temp) {
  if (smokeRaw >= SMOKE_THRESHOLD_DANGER ||
      smokePPM >= GAS_PPM_DANGER         ||
      temp     >= TEMP_THRESHOLD_DANGER) {
    return 2; // DANGER
  }
  if (smokeRaw >= SMOKE_THRESHOLD_WARN  ||
      smokePPM >= GAS_PPM_WARN          ||
      temp     >= TEMP_THRESHOLD_WARN) {
    return 1; // WARNING
  }
  return 0; // NORMAL
}

// Drive buzzer and LEDs based on alert
void handleLocalAlert(int level) {
  switch (level) {
    case 2: // DANGER — continuous alarm
      digitalWrite(LED_GREEN_PIN, LOW);
      digitalWrite(LED_RED_PIN, HIGH);
      tone(BUZZER_PIN, 1000);
      break;
    case 1: // WARNING — slow beep
      digitalWrite(LED_GREEN_PIN, LOW);
      blinkLED(LED_RED_PIN, 300);
      tone(BUZZER_PIN, 800, 200);
      break;
    default: // NORMAL
      noTone(BUZZER_PIN);
      digitalWrite(LED_RED_PIN, LOW);
      digitalWrite(LED_GREEN_PIN, HIGH);
      break;
  }
}

// POST sensor data as JSON to Flask API
void sendSensorData(float temp, float hum, int smokeRaw, float smokePPM, int alert) {
  Serial.println(F("Connecting to server..."));

  if (!client.connect(server, SERVER_PORT)) {
    Serial.println(F("Connection FAILED"));
    return;
  }

  // Build JSON payload
  StaticJsonDocument<256> doc;
  doc["device_id"]   = DEVICE_ID;
  doc["location"]    = DEVICE_LOCATION;
  doc["temperature"] = serialized(String(temp, 2));
  doc["humidity"]    = serialized(String(hum, 2));
  doc["smoke_raw"]   = smokeRaw;
  doc["smoke_ppm"]   = serialized(String(smokePPM, 2));
  doc["alert_level"] = alert;  // 0=normal,1=warning,2=danger
  doc["uptime_s"]    = millis() / 1000;

  String payload;
  serializeJson(doc, payload);

  // HTTP POST
  client.println(F("POST /api/sensor-data HTTP/1.1"));
  client.print(F("Host: ")); client.print(server); client.print(F(":")); client.println(SERVER_PORT);
  client.println(F("Content-Type: application/json"));
  client.println(F("Connection: close"));
  client.print(F("Content-Length: ")); client.println(payload.length());
  client.println();
  client.println(payload);

  // Read response (wait up to 3s)
  unsigned long timeout = millis();
  while (client.connected() && millis() - timeout < 3000) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
      if (line.startsWith(F("HTTP"))) {
        Serial.print(F("Server response: ")); Serial.println(line);
      }
      break;
    }
  }

  client.stop();
  Serial.println(F("Data sent OK"));
}

void blinkLED(int pin, int ms) {
  digitalWrite(pin, HIGH);
  delay(ms / 2);
  digitalWrite(pin, LOW);
  delay(ms / 2);
}
