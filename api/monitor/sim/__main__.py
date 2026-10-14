"""python -m monitor.sim   (env: MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD)"""

import asyncio
import logging

from monitor.sim.plant import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
asyncio.run(run())
