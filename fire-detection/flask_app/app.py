"""
Smart Fire Detection System — Flask Backend
Run: python app.py
API: POST /api/sensor-data   — Arduino sends readings
     GET  /api/readings      — Dashboard fetches data
     GET  /api/alerts        — Alert history
     POST /api/thresholds    — Update thresholds
     GET  /                  — Dashboard UI
"""

from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os, logging

app = Flask(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'fire_system.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')

db = SQLAlchemy(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── MODELS ────────────────────────────────────────────────────────────────
class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    id          = db.Column(db.Integer,   primary_key=True)
    device_id   = db.Column(db.String(50), nullable=False, default='UNKNOWN')
    location    = db.Column(db.String(100), nullable=False, default='Unspecified')
    temperature = db.Column(db.Float,    nullable=False)
    humidity    = db.Column(db.Float,    nullable=False)
    smoke_raw   = db.Column(db.Integer,  nullable=False)
    smoke_ppm   = db.Column(db.Float,    nullable=False)
    alert_level = db.Column(db.Integer,  nullable=False, default=0)
    uptime_s    = db.Column(db.Integer,  nullable=True)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'device_id':   self.device_id,
            'location':    self.location,
            'temperature': self.temperature,
            'humidity':    self.humidity,
            'smoke_raw':   self.smoke_raw,
            'smoke_ppm':   self.smoke_ppm,
            'alert_level': self.alert_level,
            'alert_label': ['NORMAL', 'WARNING', 'DANGER'][self.alert_level],
            'uptime_s':    self.uptime_s,
            'timestamp':   self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        }


class AlertEvent(db.Model):
    __tablename__ = 'alert_events'
    id          = db.Column(db.Integer,  primary_key=True)
    device_id   = db.Column(db.String(50))
    location    = db.Column(db.String(100))
    alert_level = db.Column(db.Integer,  nullable=False)
    temperature = db.Column(db.Float)
    smoke_ppm   = db.Column(db.Float)
    message     = db.Column(db.String(255))
    resolved    = db.Column(db.Boolean,  default=False)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'device_id':   self.device_id,
            'location':    self.location,
            'alert_level': self.alert_level,
            'alert_label': ['NORMAL', 'WARNING', 'DANGER'][self.alert_level],
            'temperature': self.temperature,
            'smoke_ppm':   self.smoke_ppm,
            'message':     self.message,
            'resolved':    self.resolved,
            'timestamp':   self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        }


class Threshold(db.Model):
    __tablename__ = 'thresholds'
    id                  = db.Column(db.Integer, primary_key=True)
    smoke_warn          = db.Column(db.Integer, default=300)
    smoke_danger        = db.Column(db.Integer, default=600)
    temp_warn           = db.Column(db.Float,   default=40.0)
    temp_danger         = db.Column(db.Float,   default=55.0)
    gas_ppm_warn        = db.Column(db.Float,   default=200.0)
    gas_ppm_danger      = db.Column(db.Float,   default=500.0)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── HELPERS ───────────────────────────────────────────────────────────────
def get_thresholds():
    t = Threshold.query.first()
    if not t:
        t = Threshold()
        db.session.add(t)
        db.session.commit()
    return t


def should_alert(reading: SensorReading, thresholds: Threshold) -> bool:
    """Return True if this reading triggered alert level >= 1."""
    return reading.alert_level >= 1


def log_alert_event(reading: SensorReading):
    """Create an alert event record when a reading is a warning/danger."""
    labels = {1: 'WARNING', 2: 'DANGER'}
    level = reading.alert_level
    messages = {
        1: f"Warning: Elevated smoke ({reading.smoke_ppm:.1f} ppm) or temp ({reading.temperature:.1f}°C) at {reading.location}",
        2: f"DANGER: Fire risk detected! Smoke {reading.smoke_ppm:.1f} ppm, Temp {reading.temperature:.1f}°C at {reading.location}",
    }
    event = AlertEvent(
        device_id   = reading.device_id,
        location    = reading.location,
        alert_level = level,
        temperature = reading.temperature,
        smoke_ppm   = reading.smoke_ppm,
        message     = messages.get(level, ''),
    )
    db.session.add(event)
    db.session.commit()
    logger.warning(f"ALERT EVENT [{labels[level]}]: {event.message}")


# ─── ROUTES ────────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    """Arduino POSTs JSON readings here every few seconds."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    required = ['temperature', 'humidity', 'smoke_raw', 'smoke_ppm', 'alert_level']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({'error': f'Missing fields: {missing}'}), 400

    reading = SensorReading(
        device_id   = data.get('device_id',   'UNKNOWN'),
        location    = data.get('location',    'Unspecified'),
        temperature = float(data['temperature']),
        humidity    = float(data['humidity']),
        smoke_raw   = int(data['smoke_raw']),
        smoke_ppm   = float(data['smoke_ppm']),
        alert_level = int(data['alert_level']),
        uptime_s    = data.get('uptime_s'),
    )

    db.session.add(reading)
    db.session.commit()

    thresholds = get_thresholds()
    if should_alert(reading, thresholds):
        # Only log event if previous reading was normal (avoid duplicate events)
        prev = SensorReading.query.filter_by(device_id=reading.device_id)\
                                  .order_by(SensorReading.id.desc())\
                                  .offset(1).first()
        if not prev or prev.alert_level < reading.alert_level:
            log_alert_event(reading)

    logger.info(f"[{reading.device_id}] T:{reading.temperature}°C Smoke:{reading.smoke_ppm}ppm Alert:{reading.alert_level}")

    return jsonify({'status': 'ok', 'id': reading.id}), 201


@app.route('/api/readings', methods=['GET'])
def get_readings():
    """Return latest N readings, or filter by device/time range."""
    limit     = min(int(request.args.get('limit', 60)), 500)
    device_id = request.args.get('device_id')
    hours     = int(request.args.get('hours', 1))

    since = datetime.utcnow() - timedelta(hours=hours)
    q = SensorReading.query.filter(SensorReading.timestamp >= since)
    if device_id:
        q = q.filter_by(device_id=device_id)
    readings = q.order_by(SensorReading.timestamp.desc()).limit(limit).all()

    return jsonify({
        'count':    len(readings),
        'readings': [r.to_dict() for r in reversed(readings)],
    })


@app.route('/api/readings/latest', methods=['GET'])
def get_latest():
    """Single latest reading per device."""
    device_id = request.args.get('device_id', 'SENSOR-NODE-01')
    reading = SensorReading.query.filter_by(device_id=device_id)\
                                 .order_by(SensorReading.timestamp.desc()).first()
    if not reading:
        return jsonify({'error': 'No data yet'}), 404
    return jsonify(reading.to_dict())


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Return recent alert events."""
    limit    = min(int(request.args.get('limit', 20)), 100)
    resolved = request.args.get('resolved', 'false').lower() == 'true'
    events = AlertEvent.query.filter_by(resolved=resolved)\
                             .order_by(AlertEvent.timestamp.desc())\
                             .limit(limit).all()
    return jsonify({'count': len(events), 'alerts': [e.to_dict() for e in events]})


@app.route('/api/alerts/<int:alert_id>/resolve', methods=['PATCH'])
def resolve_alert(alert_id):
    event = AlertEvent.query.get_or_404(alert_id)
    event.resolved = True
    db.session.commit()
    return jsonify({'status': 'resolved', 'id': alert_id})


@app.route('/api/thresholds', methods=['GET'])
def get_threshold_config():
    t = get_thresholds()
    return jsonify({
        'smoke_warn':     t.smoke_warn,
        'smoke_danger':   t.smoke_danger,
        'temp_warn':      t.temp_warn,
        'temp_danger':    t.temp_danger,
        'gas_ppm_warn':   t.gas_ppm_warn,
        'gas_ppm_danger': t.gas_ppm_danger,
    })


@app.route('/api/thresholds', methods=['POST'])
def update_thresholds():
    data = request.get_json(silent=True) or {}
    t = get_thresholds()
    for field in ['smoke_warn', 'smoke_danger', 'temp_warn', 'temp_danger', 'gas_ppm_warn', 'gas_ppm_danger']:
        if field in data:
            setattr(t, field, float(data[field]))
    t.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'status': 'updated'})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Summary stats for the dashboard header cards."""
    since_24h = datetime.utcnow() - timedelta(hours=24)
    total  = SensorReading.query.filter(SensorReading.timestamp >= since_24h).count()
    alerts = AlertEvent.query.filter(AlertEvent.timestamp >= since_24h).count()
    danger = AlertEvent.query.filter(
        AlertEvent.timestamp >= since_24h,
        AlertEvent.alert_level == 2
    ).count()
    latest = SensorReading.query.order_by(SensorReading.timestamp.desc()).first()

    return jsonify({
        'readings_24h': total,
        'alerts_24h':   alerts,
        'danger_24h':   danger,
        'latest':       latest.to_dict() if latest else None,
    })


# ─── INIT ──────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    get_thresholds()  # ensure default threshold row exists
    logger.info("Database initialized")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
