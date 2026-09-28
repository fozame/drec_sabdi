import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from flask import Flask  # noqa: E402

import config  # noqa: E402
from app.database import init_db  # noqa: E402

app = Flask(__name__)
app.config["SECRET_KEY"] = config.CLE_SECRETE
app.config["JSON_AS_ASCII"] = False

init_db()

from app import routes  # noqa: E402,F401
