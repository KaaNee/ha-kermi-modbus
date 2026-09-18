# Kermi (Modbus): Home Assistant Custom Component

HACS-Integration für Kermi-Wärmepumpen (x-center / x-change dynamic pro) über Modbus/TCP.
Ersetzt die klassische `modbus:`-YAML-Konfiguration durch Config Flow, echte Entities/Devices
und eine geteilte Modbus-Verbindung (`homeassistant.components.modbus`, HA 2026.9+
"Modernizing Modbus") statt eigenem Socket.

Nutzt [`kermi-modbus`](../kermi-modbus) als Device Library (reines Python, kein HA-Bezug) und
[`modbus-connection`](https://home-assistant-libs.github.io/modbus-connection/) als
Verbindungs-Framework.

> [!NOTE]
> Gegen ein echtes x-center (x-change dynamic pro) verifiziert. Siehe `kermi-modbus`s README
> und den Projektplan (Register 152, Modul-Aufteilung 50/51, Schreibpfade 302/303 + 201/203).
> Diese HA-Integration selbst (Config Flow, Coordinator, Entities) wurde am 2026-09-14 gegen
> eine echte, lokale Home-Assistant-Dev-Instanz getestet (`scripts/develop`) und live gegen das
> reale x-center verbunden: Config Flow, alle drei Devices, alle 45 Entitäten mit echten
> Live-Werten bestätigt. Ein dabei gefundener Bug (`config_flow.py`s Verbindungstest) ist
> behoben, siehe „Bekannte Einschränkungen" unten. Am 2026-09-18 zusätzlich zwei Schreibpfade
> über die HA-Entities selbst (nicht nur bibliotheksseitig) gegen das echte x-center getestet:
> `number.dhw_single_charge_setpoint` (Register 104) und `select.energy_mode` (Register 155):
> beide Schreibvorgänge sofort wirksam (Debounce-Fix bestätigt live) und mit der originalen
> Kermi-App gegen die Anlage gegengeprüft. Ebenso `switch.dhw_single_charge` (Register 103,
> löst physisch eine Ladung aus): Ein/Aus sofort wirksam bestätigt.

## Installation

`kermi-modbus` ist seit 2026-09-18 auf PyPI veröffentlicht
([pypi.org/project/kermi-modbus](https://pypi.org/project/kermi-modbus/)). `manifest.json`s
`kermi-modbus==0.0.1`-Requirement installiert sich automatisch, sobald HA die Integration lädt.
Kein manueller Schritt mehr nötig.

Als HACS Custom Repository (`Integration`, dieses Verzeichnis) hinzufügen, oder
`custom_components/kermi_modbus/` manuell nach `<config>/custom_components/` kopieren.

In HA: Einstellungen → Geräte & Dienste → Integration hinzufügen → „Kermi (Modbus)".
Host, Port (Standard 502), x-center-Unit-ID (Standard 40) eingeben. Heizkreis-Unit (50) und
TWE-Unit (51) sind optional und unabhängig: leer lassen, falls die eigene Installation eines
davon nicht hat. Verbindung wird sofort geprüft (`async_get_temporary_unit`, siehe
`config_flow.py`).

## Entities

| Domain | Gerät | Beispiele | Quelle |
|---|---|---|---|
| `sensor` | x-center | Außen-/Vor-/Rücklauftemperatur, Volumenstrom, COP (gesamt/Heizen/TWE/Kühlen), thermische + elektrische Leistung (gesamt/Heizen/TWE/Kühlen), Betriebsstunden, Gesamtstatus | `sensor.py` |
| `sensor` | Heizkreis (Unit 50, optional) | Puffer-/Kühlpuffer-Temperaturen, Heizkreisstatus/-temperaturen, Betriebsmodus, externer WEZ-Status, 4× freier Fühler (deaktiviert), Außentemperatur (roh + gemittelt), Pumpen-/Heizstab-Betriebsstunden | `sensor.py` |
| `sensor` | TWE (Unit 51, optional) | TWE-Ist-/Solltemperatur, externer WEZ-Status | `sensor.py` |
| `binary_sensor` | x-center | Alarm aktiv | `binary_sensor.py` |
| `binary_sensor` | Heizkreis | Sommerbetrieb aktiv, Kühlbetrieb aktiv | `binary_sensor.py` |
| `number` | Heizkreis | Parallelverschiebung Heizkurve, Sommer-Aus-/Winter-Ein-/Kühlen-Ein-/Kühlen-Aus-Schwellwert | `number.py` |
| `number` | TWE | Konstanter Sollwert, Einmalladung-Sollwert | `number.py` |
| `number` | x-center (nur bei aktivierter PV-Modulation) | PV-Zieltemperatur Heizen/TWE | `number.py` |
| `select` | Heizkreis | Betriebsart, Energiemodus, Manuelle Saisonauswahl, Externer-WEZ-Modus | `select.py` |
| `select` | TWE | Externer-WEZ-Modus | `select.py` |
| `switch` | TWE | Einmalladung | `switch.py` |

Damit sind alle 15 dokumentierten Schreibregister abgedeckt (project plan §9). Jeder
Schreibvorgang liest die betroffene Komponente direkt danach erneut (nicht über den
Coordinator); siehe „Architektur" unten, warum.

## Energy Dashboard einrichten

Die Kermi-Registerliste hat kein natives kWh-Register (geprüft: Excel + `kermi-modbus`s
`const.py` enthalten nur Momentanleistungen in kW, keinen Lifetime-Zähler), dieselbe Situation
wie bei `e3dc-modbus`. HA's Energy Dashboard braucht Energie-Sensoren (kWh, stetig steigend),
keine Leistungssensoren (kW); die liefert diese Integration nicht direkt.

Wichtig ist der Unterschied zwischen elektrisch und thermisch (Kermi-spezifisch, bei E3DC gab
es das nicht): die x-center-Register liefern zwei unterschiedliche Leistungsarten:

- Thermische Leistung (Register 104-107, `thermal_power*`): die von der Wärmepumpe abgegebene
  Heizleistung. Nicht für das Energy Dashboard geeignet, das würde den realen Netzbezug um
  etwa den Faktor der COP überschätzen.
- Elektrische Leistung (Register 108-111, `electric_power*`): die tatsächlich aus dem Netz
  bezogene Leistung. Das ist die richtige Größe fürs Energy Dashboard.

Die COP-Register (100-103) bestätigen diese Zuordnung: COP = thermisch / elektrisch, also
müssen beide Seiten getrennt existieren. Daher die klare Namenstrennung `thermal_power_*` vs.
`electric_power_*` in den Entity-Namen selbst, nicht nur in dieser Doku.

Zusätzliche Falle: nicht doppelt zählen. `electric_power` (108) ist bereits die Gesamtleistung;
`electric_power_heating`/`_dhw`/`_cooling` (109-111) sind deren Aufteilung nach Zweck. Für den
Energy Dashboard entweder nur `electric_power` oder die drei Teil-Sensoren verwenden, nie alle
vier gemeinsam, sonst wird der Verbrauch verdoppelt.

Der fehlende letzte Schritt, Leistung (kW) zu Energie (kWh), ist reine HA-Bordmittel, kein Code
nötig:

1. Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → Integralsensor
   (= Riemann-Summe). Eingangssensor: *Kermi x-change dynamic pro Electric power* (Register
   108), Metrisches Präfix: k (kilo) (der Sensor liefert bereits kW, also keinen zusätzlichen
   Faktor wählen, anders als bei E3DC, das in W misst), Zeiteinheit: Stunden.
2. Einstellungen → Dashboards → Energie: den neuen Helfer-Sensor bei „Stromnetz" als
   „Individuelle Geräte" oder passend zur eigenen Zählerstruktur eintragen.
3. Kann nach dem Anlegen bis zu ein paar Minuten dauern, bis die Statistik-Metadaten stehen
   (HA zeigt dazu eine gelbe, harmlose Warnung); kein Fehler.

Warum kein fertiger kWh-Sensor direkt aus der Integration? Dieselbe Begründung wie bei
`e3dc-modbus` (siehe dessen README): HA's Integral-Helfer entkoppelt die Statistik von der
Integration (Historie bricht sonst bei Integrationsänderungen), und eine eigene Akkumulation
müsste neustart-sicher persistieren (`RestoreEntity`) und HA's eigene Methode duplizieren, für
zweifelhaften Gewinn.

## Architektur

- Drei Unit-Typen statt einem (anders als `e3dc_modbus`): x-center (Pflicht) sowie Heizkreis-
  und TWE-Speichersystemmodul (je optional, unabhängig), bestätigt funktional getrennt
  (Projektplan §10.1). Bis zu drei HA-Devices pro Config Entry, Speichermodule über
  `via_device` an das x-center gebunden.
- Kein `async_probe()`: Kermi dokumentiert kein Modell-/Seriennummer-Register (siehe
  `kermi-modbus`s `models/_base.py`). `unique_id` ist deshalb `host_port_xcenter-unit`, nicht
  eine Seriennummer. Geräte-Identität bleibt stabil, solange sich diese drei nicht ändern.
- `__init__.py`: holt sich per `async_get_unit` eine geteilte Modbus-Unit pro konfigurierter
  Unit-ID von HA's `modbus`-Integration (alle auf demselben Host/Port, eine gemeinsame
  TCP-Verbindung), baut `KermiDevice` + die DeviceInfo-Objekte, startet den Coordinator.
- `coordinator.py`: `DataUpdateCoordinator[None]`, pollt einmal pro Intervall
  (`device.async_update()`, gathert intern über alle konfigurierten Units). Entities lesen live
  von `entry.runtime_data.device.xcenter.power.cop` etc.
- `entity.py`: `device_key` (`xcenter`/`heating_circuit`/`dhw`) wählt die passende `DeviceInfo`
  für jede Entity.
- `config_flow.py`: validiert mit `async_get_temporary_unit`, einmal je konfigurierter Unit.
  Options Flow für PV-Modulation-Opt-in und Poll-Intervall (Default 30s, bewusst konservativer
  als E3DCs 10s, siehe Projektplan §8: das x-center reagiert empfindlich auf Polling, und diese
  Integration liest bis zu drei Units pro Zyklus).
- `number.py`/`select.py`/`switch.py`: nach jedem Schreibvorgang liest die Entity ihre eigene
  Komponente direkt erneut (`component.async_update()` + `self.async_write_ha_state()`), nicht
  `coordinator.async_request_refresh()`. Gefunden beim Testen (2026-09-14, siehe
  `tests/test_number_select_switch.py`): HA's `DataUpdateCoordinator.async_request_refresh()`
  debounct mit 10 Sekunden Cooldown (`REQUEST_REFRESH_DEFAULT_COOLDOWN`); zwei Schreibvorgänge
  auf unterschiedliche Entities innerhalb dieses Fensters hätten sonst dazu geführt, dass die
  zuerst geschriebene Entity bis zum nächsten regulären Poll einen veralteten Wert zeigt.

## Entwicklung

```bash
scripts/setup      # installiert kermi-modbus (editable) + HA + Testabhängigkeiten
scripts/lint        # ruff format + ruff check --fix
pytest              # 10 Tests: Config Flow, Setup/Unload, number/select/switch-Schreibpfade
scripts/develop     # startet eine echte HA-Instanz mit dieser Integration in ./config/
```

Tests laufen ohne echte Hardware: `tests/conftest.py`s `mock_kermi_units`-Fixture baut drei
`modbus_connection.mock.MockModbusUnit`s (x-center/Heizkreis/TWE), die wie eine echte Kermi
antworten. `test_config_flow.py` mockt nur `async_get_temporary_unit` (HA-Core-Code, nicht
unserer); `test_init.py` fährt einen echten Config-Entry-Setup/Unload-Zyklus und prüft reale
Entity-States danach (Lookup über die Entity Registry per `unique_id`, nicht über geratene
`entity_id`-Slugs); `test_number_select_switch.py` treibt `number`/`select`/`switch` über die
echten HA-Services (`number.set_value`, `select.select_option`, `switch.turn_on`/`turn_off`),
nicht direkt über die Entity-Methoden.

## Bekannte Einschränkungen

- `number`/`select`/`switch` gegen echte Hardware getestet (2026-09-18):
  `dhw_single_charge_setpoint` (104), `energy_mode` (155) und `dhw_single_charge` (103) über
  die echten HA-Entities geschrieben, sofortige Wirksamkeit bestätigt (Debounce-Fix live
  verifiziert) und mit der originalen Kermi-App gegen die Anlage gegengeprüft. Die übrigen 8
  `number`- und 4 `select`-Entities nutzen denselben Schreibpfad (`component.write()` +
  `component.async_update()`) und wurden nicht einzeln wiederholt.
- Die Home-Assistant-eigene Warnung „calls `device_registry.async_get_or_create` with a
  deprecated `via_device` parameter" (läuft bis HA 2027.8.0) betrifft alle Plattformen mit
  einem Heizkreis-/TWE-Gerät, noch nicht auf `via_device_id` migriert.
- Gefunden und behoben beim Test gegen echte Hardware (2026-09-14): der Config-Flow-
  Verbindungstest (`config_flow.py`s `_probe_unit`) las ursprünglich für jede Unit
  `EnergySource`s x-center-Register 1-3. Auf den Heizkreis-/TWE-Units existiert Register 3
  dort nicht, die echte Hardware antwortete mit einer kürzeren PDU als angefordert
  (`Invalid register count: expected 3, got 2`), was die Einrichtung fehlschlagen ließ. Fix:
  ein domänenspezifisches Einzelregister pro Unit (200/150/100). Nur im Mock-Test nicht
  aufgefallen, weil der Mock jede angeforderte Registeranzahl anstandslos beantwortet.
- Nur x-change dynamic pro real getestet. Bösch-Sub-Marke laut eigenem openHAB-Binding "nearly
  identically", aber unverifiziert (siehe Projektplan §12/§13).
- Kaskade (Slave 41/42) nicht implementiert, kein Testgerät vorhanden.

## Lizenz

Apache-2.0, siehe `LICENSE` (entschieden 2026-09-18, dieselbe Lizenz wie `kermi-modbus` und
`ha-e3dc-modbus`).
