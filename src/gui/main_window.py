import csv
import json
from pathlib import Path
from PyQt6.QtGui import QAction
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dane.sciezka import SCIEZKA


def find_airports_csv() -> Path:
    relative_target = Path("dane") / "lotniska.csv"
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / relative_target
        if candidate.exists():
            return candidate
        samoloty_candidate = parent / "Samoloty_Najw_Zysk" / relative_target
        if samoloty_candidate.exists():
            return samoloty_candidate
    return Path.cwd() / relative_target


AIRPORTS_CSV_PATH = find_airports_csv()


def load_airports_from_csv(csv_path: Path = AIRPORTS_CSV_PATH) -> dict[str, dict]:
    if not csv_path.exists():
        return {}

    airports_by_code = {}
    with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            icao = (row.get("icao_code") or "").strip().upper()
            lat_raw = row.get("latitude")
            lon_raw = row.get("longitude")
            if not icao or not lat_raw or not lon_raw:
                continue
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except ValueError:
                continue

            airports_by_code[icao] = {
                "icao_code": icao,
                "airport_name": (row.get("airport_name") or icao).strip(),
                "latitude": lat,
                "longitude": lon,
            }
    return airports_by_code


def build_path_segments(path_codes: list[str], airports_by_code: dict[str, dict]) -> list[dict]:
    segments = []
    for idx in range(len(path_codes) - 1):
        from_code = (path_codes[idx] or "").strip().upper()
        to_code = (path_codes[idx + 1] or "").strip().upper()
        dep = airports_by_code.get(from_code)
        arr = airports_by_code.get(to_code)
        if not dep or not arr:
            continue

        segments.append({
            "step": idx + 1,
            "callsign": f"Step {idx + 1}",
            "from_code": from_code,
            "to_code": to_code,
            "from_name": dep["airport_name"],
            "to_name": arr["airport_name"],
            "from_lat": dep["latitude"],
            "from_lon": dep["longitude"],
            "to_lat": arr["latitude"],
            "to_lon": arr["longitude"],
            "same_point": from_code == to_code,
        })
    return segments


MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Flights Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; padding: 0; background: #1e2229; }
  .pin-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .pin-dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2.5px solid #ffffff;
    box-shadow: 0 0 5px rgba(0, 0, 0, 0.75);
  }
  .arrow-icon {
    font-size: 18px;
    font-weight: bold;
    text-shadow: 0 0 3px #ffffff, 0 0 6px #ffffff;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
  const map = L.map('map', { worldCopyJump: true }).setView([25, 10], 2);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© OpenStreetMap'
  }).addTo(map);

  const flightLayer = L.layerGroup().addTo(map);

  const ROUTE_COLORS = [
    '#1e88e5', '#2e7d32', '#e53935', '#8e24aa',
    '#fb8c00', '#00897b', '#3949ab', '#c0ca33',
    '#d81b60', '#6d4c41', '#039be5', '#43a047'
  ];

  function pickColor(index, prevColor) {
    let color = ROUTE_COLORS[(index * 5) % ROUTE_COLORS.length];
    if (color === prevColor) {
      color = ROUTE_COLORS[(index * 5 + 1) % ROUTE_COLORS.length];
    }
    return color;
  }

  function createPinIcon(color) {
    return L.divIcon({
      className: 'pin-wrapper',
      html: `<div class="pin-dot" style="background-color: ${color};"></div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9]
    });
  }

  function screenAngleDeg(lat1, lon1, lat2, lon2) {
    const pt1 = map.latLngToLayerPoint([lat1, lon1]);
    const pt2 = map.latLngToLayerPoint([lat2, lon2]);
    const dx = pt2.x - pt1.x;
    const dy = pt2.y - pt1.y;
    return Math.atan2(dy, dx) * (180 / Math.PI);
  }

  function renderFlights(flights) {
    flightLayer.clearLayers();
    let prevColor = null;
    const bounds = [];

    flights.forEach((f, idx) => {
      const fromLat = Number(f.from_lat);
      const fromLon = Number(f.from_lon);
      const toLat = Number(f.to_lat);
      const toLon = Number(f.to_lon);

      if ([fromLat, fromLon, toLat, toLon].some(Number.isNaN)) {
        return;
      }

      const color = pickColor(idx, prevColor);
      prevColor = color;

      const p1 = [fromLat, fromLon];
      const p2 = [toLat, toLon];
      bounds.push(p1, p2);

      const popupHtml = `<b>${f.callsign || 'Step'}</b><br>${f.from_code} → ${f.to_code}`;

      const dashedLine = L.polyline([p1, p2], {
        color: color,
        weight: 2.5,
        opacity: 0.9,
        dashArray: '8, 8'
      }).addTo(flightLayer);
      dashedLine.bindPopup(popupHtml);

      const pinIcon = createPinIcon(color);
      L.marker(p1, { icon: pinIcon })
        .bindPopup(`<b>${f.from_code} (${f.from_name || ''})</b><br>lat: ${fromLat}, lon: ${fromLon}`)
        .addTo(flightLayer);

      L.marker(p2, { icon: pinIcon })
        .bindPopup(`<b>${f.to_code} (${f.to_name || ''})</b><br>lat: ${toLat}, lon: ${toLon}`)
        .addTo(flightLayer);

      if (!f.same_point) {
        const midLat = (fromLat + toLat) / 2;
        const midLon = (fromLon + toLon) / 2;
        const angle = screenAngleDeg(fromLat, fromLon, toLat, toLon);

        const arrowIcon = L.divIcon({
          className: '',
          html: `<div class="arrow-icon" style="color: ${color}; transform: rotate(${angle}deg); line-height: 20px; text-align: center;">➤</div>`,
          iconSize: [20, 20],
          iconAnchor: [10, 10]
        });

        L.marker([midLat, midLon], { icon: arrowIcon, interactive: false }).addTo(flightLayer);
      }
    });

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [35, 35] });
    }
  }
</script>
</body>
</html>
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flight Analytics - Path Map")
        self.resize(1280, 760)
        self.airports_by_code = load_airports_from_csv()

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.web_view = QWebEngineView()
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.web_view.setHtml(MAP_HTML)
        self.web_view.loadFinished.connect(lambda ok: self.draw_path_from_csv() if ok else None)
        root_layout.addWidget(self.web_view, stretch=1)

        right_panel = QFrame()
        right_panel.setFixedWidth(220)
        right_panel.setStyleSheet("background-color: #2b2f36; color: #f0f0f0;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        # Przykładowe przyciski bez podpięć
        for label in ["Przycisk 1", "Przycisk 2", "Przycisk 3"]:
            btn = QPushButton(label)
            btn.setMinimumHeight(38)
            right_layout.addWidget(btn)

        right_layout.addStretch()
        root_layout.addWidget(right_panel)

    def draw_path_from_csv(self):
        segments = build_path_segments(SCIEZKA, self.airports_by_code)
        payload = json.dumps(segments, ensure_ascii=False)
        self.web_view.page().runJavaScript(f"renderFlights({payload});")