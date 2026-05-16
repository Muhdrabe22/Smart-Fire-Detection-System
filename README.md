# 🔥 Smart Fire Detection System

A production-ready full-stack fire detection system using **Arduino Uno + Ethernet Shield**, **MQ-2/MQ-135 smoke/gas sensors**, **DHT22 temperature sensor**, and a **Python Flask** web dashboard.

---

## 📐 Architecture

```
[Arduino Uno]
  ├── MQ-2 Sensor (Smoke/Gas) → A0
  ├── DHT22 Sensor (Temp/Humidity) → D2
  ├── Buzzer → D7
  ├── Red LED → D8
  └── Green LED → D9
        │
        │ HTTP POST /api/sensor-data (JSON, every 5s)
        ▼
[Ethernet Shield W5100] ─────► [Flask Server :5000]
                                   ├── SQLite Database
                                   ├── Alert Engine
                                   └── Web Dashboard
                                          │
                                          ▼
                                   Browser (live charts,
                                   alert history, threshold config)
```

---

## ⚡ Hardware Wiring

| Component  | Pin   | Arduino |
|------------|-------|---------|
| MQ-2 VCC   | 5V    | 5V      |
| MQ-2 GND   | GND   | GND     |
| MQ-2 AOUT  | A0    | A0      |
| DHT22 VCC  | 5V    | 5V      |
| DHT22 GND  | GND   | GND     |
| DHT22 DATA | D2    | D2 (+ 10kΩ pull-up to 5V) |
| Buzzer +   | D7    | D7      |
| Red LED    | D8    | D8 (+ 220Ω resistor)       |
| Green LED  | D9    | D9 (+ 220Ω resistor)       |

---

## 🖥️ Flask Setup

```bash
cd flask_app
pip install -r requirements.txt
python app.py
```

Dashboard will be at: **http://localhost:5000**

For production (use gunicorn):
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

---

## 🔌 Arduino Setup

### Libraries Required (install via Library Manager):
- **DHT sensor library** by Adafruit
- **ArduinoJson** by Benoit Blanchon (v6+)
- **Ethernet** (built-in)

### Steps:
1. Open `arduino/fire_detection.ino` in Arduino IDE
2. Update these values at the top of the file:
   ```cpp
   IPAddress ip(192, 168, 1, 177);     // Arduino's desired static IP
   IPAddress server(192, 168, 1, 100); // Flask server's IP address
   const int SERVER_PORT = 5000;
   ```
3. If using **DHT11** instead of DHT22, change:
   ```cpp
   #define DHT_TYPE DHT11
   ```
4. Upload to Arduino Uno

---

## 📡 API Endpoints

| Method | Endpoint                        | Description                     |
|--------|---------------------------------|---------------------------------|
| POST   | `/api/sensor-data`              | Arduino sends readings (JSON)   |
| GET    | `/api/readings`                 | Fetch recent readings           |
| GET    | `/api/readings/latest`          | Latest reading for a device     |
| GET    | `/api/alerts`                   | Alert event history             |
| PATCH  | `/api/alerts/<id>/resolve`      | Mark alert as resolved          |
| GET    | `/api/thresholds`               | Get threshold config            |
| POST   | `/api/thresholds`               | Update thresholds               |
| GET    | `/api/stats`                    | 24h summary stats               |

### Sample Arduino POST payload:
```json
{
  "device_id":   "SENSOR-NODE-01",
  "location":    "Server Room",
  "temperature": 28.5,
  "humidity":    62.3,
  "smoke_raw":   145,
  "smoke_ppm":   142.0,
  "alert_level": 0,
  "uptime_s":    3600
}
```

---

## ⚙️ Alert Levels

| Level | Label   | Meaning                                 |
|-------|---------|-----------------------------------------|
| 0     | NORMAL  | All readings within safe range          |
| 1     | WARNING | Elevated smoke or temperature           |
| 2     | DANGER  | Critical fire risk — immediate action   |

Default thresholds (adjustable from dashboard):
- Temp warn: **40°C** | danger: **55°C**
- Smoke raw warn: **300** | danger: **600**
- Gas PPM warn: **200** | danger: **500**

---

## 🚀 Production Deployment (VPS: DigitalOcean / Hetzner)

```bash
# Install dependencies
sudo apt update && sudo apt install python3-pip nginx

# Setup Flask app as systemd service
sudo nano /etc/systemd/system/fireguard.service
```

```ini
[Unit]
Description=FireGuard Fire Detection System
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/fireguard/flask_app
ExecStart=/usr/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable fireguard
sudo systemctl start fireguard
```

Configure Nginx to proxy port 80 → 5000.

---

## 🛠️ Troubleshooting

| Issue | Fix |
|-------|-----|
| MQ-2 always high | Let it warm up 30–60 seconds before readings |
| DHT read fails | Check 10kΩ pull-up resistor on DATA pin |
| Arduino can't connect | Verify Flask server IP in `server` variable |
| No data in dashboard | Check Serial Monitor — look for "Data sent OK" |
| Smoke PPM inaccurate | Calibrate Rs/Ro ratio for your environment |
