import os

class Config:
    SECRET_KEY = "dev"
    DATABASE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "instance",
        "app.sqlite"
    )